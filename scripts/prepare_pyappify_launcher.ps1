param(
    [string]$Version = "v1.2.3",
    # The version our patched launcher reports. Installed launchers replace
    # themselves only with a higher one (ok's update_pyappify), so bump this
    # whenever the launcher patches below change.
    [string]$LauncherVersion = "1.2.8",
    [string]$BuildDir = "pyappify_build",
    [ValidateSet("zlib", "lzma")]
    [string]$NsisCompression = "lzma",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Test-Path -LiteralPath $cargoBin) -and ($env:PATH -notlike "*$cargoBin*")) {
    $env:PATH = "$cargoBin;$env:PATH"
}

function Ensure-Command {
    param(
        [string]$Name,
        [string]$InstallDescription
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found. $InstallDescription"
    }
}

function Ensure-Pnpm {
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        return
    }

    Ensure-Command -Name "npm" -InstallDescription "Install Node.js/npm first."
    npm install -g pnpm
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install pnpm."
    }
    Ensure-Command -Name "pnpm" -InstallDescription "npm installed pnpm, but it is still not available on PATH."
}

function Ensure-Cargo {
    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        return
    }

    $isWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )
    if (-not $isWindows) {
        throw "cargo is required but was not found. Install Rust before running this script."
    }

    $rustupInitPath = Join-Path ([System.IO.Path]::GetTempPath()) "rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $rustupInitPath
    & $rustupInitPath -y --no-modify-path --default-toolchain stable
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Rust."
    }

    if ((Test-Path -LiteralPath $cargoBin) -and ($env:PATH -notlike "*$cargoBin*")) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
    Ensure-Command -Name "cargo" -InstallDescription "Rust was installed, but cargo is still not available on PATH."
}

function Update-InstallerNsiTemplate {
    param(
        [string]$BuildDirPath
    )

    # BUG-20260905-06: the upstream pyappify/Tauri NSIS template aborts with a bare
    # "unable to uninstall" message when the previous install's registered
    # uninstaller no longer exists (deleted install dir, moved app, ...), which
    # hard-blocks upgrading users. Patch the template right after cloning so the
    # generated installer tolerates stale uninstall entries. Every patch must hit
    # exactly once or the build fails loudly - a silently skipped patch would ship
    # an unfixed installer.

    $nsiPath = Join-Path $BuildDirPath "src-tauri\nsis\installer.nsi"
    if (-not (Test-Path -LiteralPath $nsiPath)) {
        throw "installer.nsi template not found at $nsiPath"
    }

    # -Encoding UTF8 is required: the template is UTF-8 (it already contains
    # Chinese messages) and Windows PowerShell would otherwise decode it as ANSI.
    $content = (Get-Content -LiteralPath $nsiPath -Raw -Encoding UTF8) -replace "`r`n", "`n"

    $uninstallBranchSearch = @'
    ${Else}
      ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
      ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"
      ${IfThen} $UpdateMode = 1 ${|} StrCpy $R1 "$R1 /UPDATE" ${|} ; append /UPDATE
      ${IfThen} $PassiveMode = 1 ${|} StrCpy $R1 "$R1 /P" ${|} ; append /P
      StrCpy $R1 "$R1 _?=$4" ; append uninstall directory
      ExecWait '$R1' $0
    ${EndIf}
'@
    $uninstallBranchReplacement = @'
    ${Else}
      ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
      ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"

      ; BUG-20260905-06: tolerate a stale/malformed previous-uninstall entry.
      ; $R3 = UninstallString with surrounding quotes stripped ($R1 keeps the
      ; registered form for the ExecWait command below).
      StrCpy $R3 $R1
      StrCpy $R2 $R3 1
      ${If} $R2 == "$\""
        StrCpy $R3 $R3 "" 1
        StrCpy $R3 $R3 -1
      ${EndIf}

      ; When the previous install dir is unknown, derive it from the registered
      ; uninstaller path instead of appending an empty _?= which makes the old
      ; uninstaller delete nothing.
      ${If} $4 == ""
      ${AndIf} $R3 != ""
        ${GetParent} "$R3" $4
      ${EndIf}

      ; If the registered uninstaller no longer exists, drop the stale keys and
      ; continue installing without uninstalling; ExecWait would otherwise fail
      ; with "unable to uninstall" and hard-block the upgrade.
      ${IfNot} ${FileExists} "$R3"
        DetailPrint "Previous uninstaller not found ($R3); cleaning stale uninstall entries and installing without uninstalling."
        DeleteRegKey SHCTX "${UNINSTKEY}"
        DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
        Goto reinst_uninstall_skipped
      ${EndIf}

      ${IfThen} $UpdateMode = 1 ${|} StrCpy $R1 "$R1 /UPDATE" ${|} ; append /UPDATE
      ${IfThen} $PassiveMode = 1 ${|} StrCpy $R1 "$R1 /P" ${|} ; append /P
      StrCpy $R1 "$R1 _?=$4" ; append uninstall directory
      ExecWait '$R1' $0
    ${EndIf}
'@

    $failureMessageSearch = @'
      ; Other erros? show generic error message and return to select un/reinstall page
      MessageBox MB_ICONEXCLAMATION "$(unableToUninstall)"
      Abort
    ${EndIf}
  reinst_done:
'@
    $failureMessageReplacement = @'
      ; Other erros? show generic error message and return to select un/reinstall page
      ; BUG-20260905-06: actionable guidance instead of the bare unableToUninstall message
      ${If} $LANGUAGE == 2052
        MessageBox MB_ICONEXCLAMATION "无法自动卸载旧版本。$\r$\n$\r$\n请先关闭正在运行的 ${PRODUCTNAME}，点击「上一步」重试；或返回后改选「请勿卸载」直接覆盖安装；也可手动卸载旧版后重新运行本安装包。"
      ${Else}
        MessageBox MB_ICONEXCLAMATION "Unable to uninstall the previous version.$\r$\n$\r$\nClose any running ${PRODUCTNAME}, click Back and retry; or go back, choose not to uninstall and install over it; or uninstall the old version manually and run this installer again."
      ${EndIf}
      Abort
    ${EndIf}

  reinst_uninstall_skipped:
  reinst_done:
'@

    $patches = @(
        @{ Description = "dangling uninstaller guard"; Search = $uninstallBranchSearch; Replacement = $uninstallBranchReplacement },
        @{ Description = "actionable failure message"; Search = $failureMessageSearch; Replacement = $failureMessageReplacement }
    )

    foreach ($patch in $patches) {
        # Normalize line endings on both sides: the .ps1 file may be CRLF while the
        # cloned template is LF, and here-string literals inherit the script's endings.
        $search = $patch.Search -replace "`r`n", "`n"
        $replacement = $patch.Replacement -replace "`r`n", "`n"
        $matchCount = [regex]::Matches($content, [regex]::Escape($search)).Count
        if ($matchCount -ne 1) {
            $firstLine = ($search -split "`n")[0]
            throw "installer.nsi patch '$($patch.Description)' expected exactly 1 match but found $matchCount (content=$($content.Length) chars, search=$($search.Length) chars, firstLineIndex=$($content.IndexOf($firstLine))). The pyappify template changed; update the embedded patch text."
        }
        $content = $content.Replace($search, $replacement)
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($nsiPath, ($content -replace "`n", "`r`n"), $utf8NoBom)
    Write-Host "Patched installer.nsi template for stale uninstaller tolerance (BUG-20260905-06)."
}

function Assert-UnderWorkspace {
    param(
        [string]$PathToCheck,
        [string]$Workspace
    )

    $resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
    $parent = Split-Path -Parent $PathToCheck
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $resolvedParent = (Resolve-Path -LiteralPath $parent).Path
    if (-not $resolvedParent.StartsWith($resolvedWorkspace, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside workspace: $PathToCheck"
    }
}

$workspace = (Resolve-Path -LiteralPath ".").Path
$buildPath = Join-Path $workspace $BuildDir
Assert-UnderWorkspace -PathToCheck $buildPath -Workspace $workspace

$configPath = Join-Path $workspace "pyappify.yml"
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "pyappify.yml not found at $configPath"
}

$configText = Get-Content -LiteralPath $configPath -Raw
$appNameMatch = [regex]::Match($configText, '(?m)^\s*name:\s*["'']?([^"''\r\n]+)["'']?\s*$')
if (-not $appNameMatch.Success) {
    throw "Could not read application name from pyappify.yml"
}
$appName = $appNameMatch.Groups[1].Value.Trim()
$requiresUac = [regex]::IsMatch($configText, '(?m)^\s*uac:\s*true\s*$')

Ensure-Pnpm
Ensure-Cargo

if (Test-Path -LiteralPath $buildPath) {
    Remove-Item -LiteralPath $buildPath -Recurse -Force
}

git clone https://github.com/ok-oldking/pyappify.git $buildPath
git -C $buildPath checkout "tags/$Version"

$assetConfigPath = Join-Path $buildPath "src-tauri\assets\pyappify.yml"
Copy-Item -LiteralPath $configPath -Destination $assetConfigPath -Force

$iconsSource = Join-Path $workspace "icons"
if (Test-Path -LiteralPath $iconsSource) {
    $iconsTarget = Join-Path $buildPath "src-tauri\icons"
    if (Test-Path -LiteralPath $iconsTarget) {
        Remove-Item -LiteralPath $iconsTarget -Recurse -Force
    }
    Copy-Item -LiteralPath $iconsSource -Destination $iconsTarget -Recurse -Force
}

$tauriConfPath = Join-Path $buildPath "src-tauri\tauri.conf.json"
$tauriConf = Get-Content -LiteralPath $tauriConfPath -Raw
$tauriConf = $tauriConf.Replace('"pyappify"', '"' + $appName + '"')
$tauriConf = $tauriConf.Replace('"0.0.1"', '"' + $LauncherVersion.TrimStart("v") + '"')
$tauriConfObject = $tauriConf | ConvertFrom-Json
$tauriConfObject.bundle.windows.nsis | Add-Member `
    -MemberType NoteProperty `
    -Name compression `
    -Value $NsisCompression `
    -Force
$tauriConf = $tauriConfObject | ConvertTo-Json -Depth 100
Set-Content -LiteralPath $tauriConfPath -Value $tauriConf -Encoding UTF8

$cargoTomlPath = Join-Path $buildPath "src-tauri\Cargo.toml"
$cargoToml = Get-Content -LiteralPath $cargoTomlPath -Raw
$cargoToml = $cargoToml.Replace('name = "pyappify"', 'name = "' + $appName + '"')
Set-Content -LiteralPath $cargoTomlPath -Value $cargoToml -Encoding UTF8

$packageJsonPath = Join-Path $buildPath "package.json"
$packageJson = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
if (-not $packageJson.pnpm) {
    $packageJson | Add-Member -MemberType NoteProperty -Name pnpm -Value ([pscustomobject]@{})
}
$onlyBuiltDependencies = @()
if ($packageJson.pnpm.onlyBuiltDependencies) {
    $onlyBuiltDependencies = @($packageJson.pnpm.onlyBuiltDependencies)
}
if ($onlyBuiltDependencies -notcontains "esbuild") {
    $onlyBuiltDependencies += "esbuild"
}
$packageJson.pnpm | Add-Member -MemberType NoteProperty -Name onlyBuiltDependencies -Value @($onlyBuiltDependencies | Sort-Object -Unique) -Force
$packageJson | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $packageJsonPath -Encoding UTF8

if ($requiresUac) {
    $buildRsPath = Join-Path $buildPath "src-tauri\build.rs"
    $buildRs = Get-Content -LiteralPath $buildRsPath -Raw
    $buildRs = $buildRs.Replace("const UAC: bool = false;", "const UAC: bool = true;")
    Set-Content -LiteralPath $buildRsPath -Value $buildRs -Encoding UTF8
}

$viteConfigPath = Join-Path $buildPath "vite.config.ts"
$viteConfig = Get-Content -LiteralPath $viteConfigPath -Raw
if ($viteConfig -notmatch 'base:\s*["'']\./["'']') {
    $viteConfig = $viteConfig -replace 'plugins:\s*\[react\(\)\],', "plugins: [react()],`r`n  base: `"./`","
    Set-Content -LiteralPath $viteConfigPath -Value $viteConfig -Encoding UTF8
}

# The launcher's footer linked to PyAppify's own repository; players read it
# as the tool's page (Leo 10-08), and Leo 10-09 asked to drop it altogether.
# appVersion stays referenced: the launcher is type-checked with noUnusedLocals.
$appTsxPath = Join-Path $buildPath "src\App.tsx"
$appTsx = Get-Content -LiteralPath $appTsxPath -Raw
$footerLink = '<Link href="https://github.com/ok-oldking/pyappify" target="_blank" rel="noopener noreferrer">{t(''appMadeWith'', {name: `PyAppify ${appVersion}`})}</Link>'
if (-not $appTsx.Contains($footerLink)) {
    throw "PyAppify footer link not found in App.tsx; update prepare_pyappify_launcher.ps1."
}
$appTsx = $appTsx.Replace(
    $footerLink,
    '{appVersion && null}'
)
Set-Content -LiteralPath $appTsxPath -Value $appTsx -Encoding UTF8

$appServicePath = Join-Path $buildPath "src-tauri\src\app_service.rs"
$libRsPath = Join-Path $buildPath "src-tauri\src\lib.rs"
$gitRsPath = Join-Path $buildPath "src-tauri\src\git.rs"
$loggerRsPath = Join-Path $buildPath "src-tauri\src\utils\logger.rs"
$pythonEnvRsPath = Join-Path $buildPath "src-tauri\src\python_env.rs"
$i18nPath = Join-Path $buildPath "src\i18n.ts"

# Every patch below must hit exactly once, or the build fails loudly (the old
# hide-window patch searched text v1.2.3 no longer has and silently did nothing).
function Replace-Once([string]$Text, [string]$Search, [string]$Replacement, [string]$What) {
    $count = ([regex]::Matches($Text, [regex]::Escape($Search))).Count
    if ($count -ne 1) {
        throw "Launcher patch '$What' expected exactly 1 match but found $count; update prepare_pyappify_launcher.ps1."
    }
    return $Text.Replace($Search, $Replacement)
}

# git on Windows may check the sources out with CRLF; the searches below are LF.
$appService = (Get-Content -LiteralPath $appServicePath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$libRs = (Get-Content -LiteralPath $libRsPath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$gitRs = (Get-Content -LiteralPath $gitRsPath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$loggerRs = (Get-Content -LiteralPath $loggerRsPath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$pythonEnvRs = (Get-Content -LiteralPath $pythonEnvRsPath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$appTsx = (Get-Content -LiteralPath $appTsxPath -Raw -Encoding UTF8) -replace "`r`n", "`n"
$i18n = (Get-Content -LiteralPath $i18nPath -Raw -Encoding UTF8) -replace "`r`n", "`n"

# Start the installed version when GitHub can't be reached (player report
# 2026-10-10: 「启动应用」 stayed grey). Every open fetched the tags first and
# gave up on a failed fetch, so an install whose network can't reach GitHub
# (the Full setup from a mainland network, or an accelerator turned off later)
# never learned its own version: the start button stayed disabled and auto
# start never ran. A failed fetch now falls back to the tags already on disk.
$gitRs = Replace-Once $gitRs `
    (@'
        remote
            .fetch(
                &["+refs/tags/*:refs/tags/*"],
                Some(&mut fetch_options),
                None,
            )
            .with_context(|| {
                format!(
                    "Failed to fetch tags for repository {}",
                    repo_path_for_task.display()
                )
            })?;
        prune_deleted_local_tags_from_remote(&repo, "origin", &app_name_for_task)?;
'@ -replace "`r`n", "`n") `
    (@'
        match remote.fetch(
            &["+refs/tags/*:refs/tags/*"],
            Some(&mut fetch_options),
            None,
        ) {
            Ok(()) => prune_deleted_local_tags_from_remote(&repo, "origin", &app_name_for_task)?,
            Err(e) => {
                warn!(
                    "Failed to fetch tags for repository {}, using the local tags: {}",
                    repo_path_for_task.display(),
                    e
                );
                emit_info!(
                    app_name_for_task,
                    "Cannot reach the update server; using the installed version."
                );
            }
        }
'@ -replace "`r`n", "`n") `
    "use local tags when the tag fetch fails"

# The install sat at 「Receiving objects: 99.9%」 (player report 2026-10-13).
# The progress line only moved in 0.1 steps and 100.0 - 99.9 is just under
# 0.1 in floating point, so 100% never showed, and the steps after the
# download (unpacking, writing the files) printed nothing. A download that
# stopped getting data also waited forever: libgit2 has no read timeout.
# Now 100% shows, unpacking and writing files show their own progress, and a
# stalled download gives up after a minute with the 「连不上 GitHub」 message.
$gitRs = Replace-Once $gitRs `
    (@'
        .clone();
    let _guard = lock_arc.lock().await;

    let profile = app.get_current_profile_settings();
'@ -replace "`r`n", "`n") `
    (@'
        .clone();
    let _guard = lock_arc.lock().await;

    // A download that stops getting data gives up after a minute instead of
    // waiting forever (libgit2 has no read timeout by default).
    // SAFETY: only sets libgit2's global timeout values.
    if let Err(e) = unsafe { git2::opts::set_server_timeout_in_milliseconds(60_000) } {
        warn!("Could not set the git read timeout: {}", e);
    }
    let profile = app.get_current_profile_settings();
'@ -replace "`r`n", "`n") `
    "give up on a stalled download"
$gitRs = Replace-Once $gitRs `
    (@'
        let app_name_for_progress_clone = app_name_for_messages.clone();
        callbacks.transfer_progress({
            let mut last_percent = -1.0;
            move |progress: Progress| {
'@ -replace "`r`n", "`n") `
    (@'
        let app_name_for_progress_clone = app_name_for_messages.clone();
        callbacks.transfer_progress({
            let mut last_percent = -1.0;
            let mut last_deltas_percent = usize::MAX;
            move |progress: Progress| {
'@ -replace "`r`n", "`n") `
    "track unpacking progress"
$gitRs = Replace-Once $gitRs `
    (@'
                if total_objects > 0 {
                    let current_percent = (received_objects as f64 * 100.0) / total_objects as f64;
                    let rounded_percent = (current_percent * 10.0).round() / 10.0;
                    if (rounded_percent - last_percent).abs() >= 0.1 {
                        emit_update_info!(
'@ -replace "`r`n", "`n") `
    (@'
                if total_objects > 0 {
                    let current_percent = (received_objects as f64 * 100.0) / total_objects as f64;
                    let rounded_percent = (current_percent * 10.0).round() / 10.0;
                    let all_received = received_objects == total_objects;
                    if all_received && progress.total_deltas() > 0 {
                        let deltas_percent =
                            progress.indexed_deltas() * 100 / progress.total_deltas();
                        if deltas_percent != last_deltas_percent {
                            emit_update_info!(
                                app_name_for_progress_clone,
                                "\rDownloaded {}. Unpacking files: {}%... ",
                                format_bytes(received_bytes),
                                deltas_percent
                            );
                            last_deltas_percent = deltas_percent;
                        }
                    } else if (rounded_percent - last_percent).abs() >= 0.1
                        || (all_received && last_percent < 100.0)
                    {
                        emit_update_info!(
'@ -replace "`r`n", "`n") `
    "show 100% and the unpacking step"
$gitRs = Replace-Once $gitRs `
    (@'
        let mut builder = git2::build::RepoBuilder::new();
        builder.fetch_options(fetch_options);
        builder.bare(false);

'@ -replace "`r`n", "`n") `
    (@'
        let mut builder = git2::build::RepoBuilder::new();
        builder.fetch_options(fetch_options);
        builder.bare(false);
        let app_name_for_checkout = app_name_for_messages.clone();
        let mut last_checkout_percent = usize::MAX;
        let mut checkout = CheckoutBuilder::new();
        checkout.progress(move |_path, done, total| {
            if total > 0 {
                let percent = done * 100 / total;
                if percent != last_checkout_percent {
                    emit_update_info!(
                        app_name_for_checkout,
                        "\rWriting files: {}% ({} / {})... ",
                        percent,
                        done,
                        total
                    );
                    last_checkout_percent = percent;
                }
            }
        });
        builder.with_checkout(checkout);

'@ -replace "`r`n", "`n") `
    "show the files being written"
$appService = Replace-Once $appService `
    ("        ensure_repository(&app).await?;`n        let previous_known_version = app.current_version.clone();") `
    ("        if let Err(e) = ensure_repository(&app).await {`n" +
     "            warn!(`n" +
     "                `"Could not update the repository of '{}', continuing with the local copy: {:?}`",`n" +
     "                app.name, e`n" +
     "            );`n" +
     "        }`n" +
     "        let previous_known_version = app.current_version.clone();") `
    "open with the local copy when the fetch fails"

# Download again when an earlier install stopped halfway (player report
# 2026-10-10: install failed with 「Could not open requirements file」). A
# clone that is cut off (launcher closed, PC asleep, network dropped) leaves a
# repo folder that git can open but whose files are missing; the next install
# saw the folder, only fetched, and copied the missing files on to pip. Setup
# now checks the files against the checked-out version and clones again when
# any are missing; if that still fails it says what the player can do.
# A failed download said only 「Failed to fetch updates for …\repo」 (player
# report 2026-10-11) and hid the reason; it now says GitHub could not be
# reached, what to do, and the underlying git error.
$appService = Replace-Once $appService `
    (@'
#[tauri::command]
pub async fn setup_app(app_name: &str, profile_name: &str) -> Result<(), Error> {
'@ -replace "`r`n", "`n") `
    (@'
async fn ensure_repository_for_setup(app: &App) -> Result<(), Error> {
    ensure_repository(app).await.map_err(|e| {
        err!(
            "下载失败，多半是连不上 GitHub：请先开加速器或换个网络，再按一次安装。Download failed, most likely GitHub cannot be reached: turn on an accelerator or try another network, then press install again. ({:#})",
            e
        )
    })
}

fn repo_checkout_complete(repo_path: &Path) -> bool {
    let Ok(repo) = git2::Repository::open(repo_path) else {
        return false;
    };
    let Ok(tree) = repo.head().and_then(|head| head.peel_to_tree()) else {
        return false;
    };
    let missing = match repo.diff_tree_to_workdir(Some(&tree), None) {
        Ok(diff) => diff
            .deltas()
            .any(|delta| delta.status() == git2::Delta::Deleted),
        Err(_) => true,
    };
    !missing
}

#[tauri::command]
pub async fn setup_app(app_name: &str, profile_name: &str) -> Result<(), Error> {
'@ -replace "`r`n", "`n") `
    "check the downloaded files"
$appService = Replace-Once $appService `
    (@'
    ensure_repository(&app).await?;

    let working_dir_path = get_app_working_dir_path(app_name);
'@ -replace "`r`n", "`n") `
    (@'
    ensure_repository_for_setup(&app).await?;
    if !repo_checkout_complete(&repo_path) {
        warn!(
            "Repository for '{}' at {} is missing files (an earlier download stopped halfway). Downloading it again.",
            app_name,
            repo_path.display()
        );
        emit_info!(
            app_name,
            "The last download did not finish; downloading again."
        );
        delete_dir_if_exist(&repo_path).await?;
        ensure_repository_for_setup(&app).await?;
        if !repo_checkout_complete(&repo_path) {
            return Err(err!(
                "下载不完整：请确认能连上 GitHub（可以先开加速器），再按一次安装。The download is incomplete: make sure GitHub can be reached, then press install again."
            ));
        }
    }

    let working_dir_path = get_app_working_dir_path(app_name);
'@ -replace "`r`n", "`n") `
    "download again when the files are missing"

# Update before starting, even when 「启动应用」 is pressed during the update
# check (player report 2026-10-10: auto start ticked, v0.1.11 started although
# v0.1.17 was out, and the update had to be clicked by hand). The auto update
# and the auto start only run once the tags are fetched, but the button is
# live as soon as the window shows the installed version, and start_app marks
# that check done: a press during the fetch started the old version and the
# check (update and auto start alike) was skipped. A start now waits for the
# check, so the newest version is installed first when the update method
# updates by itself (自动更新, the default), then the tool starts; when GitHub
# can't be reached the check uses the local tags (above) and the installed
# version starts.
$appService = Replace-Once $appService `
    'static AUTO_START_CANCELLED: AtomicBool = AtomicBool::new(false);' `
    ('static AUTO_START_CANCELLED: AtomicBool = AtomicBool::new(false);' + "`n" +
     'static STARTUP_CHECK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));') `
    "startup check lock"
$appService = Replace-Once $appService `
    ("    emit_app().await;`n`n    if update_app_from_disk().await? {") `
    ("    emit_app().await;`n`n    let _startup_check = STARTUP_CHECK.lock().await;`n    if update_app_from_disk().await? {") `
    "hold the startup check from the fetch on"
$appService = Replace-Once $appService `
    ("pub async fn start_app(app_handle: AppHandle, app_name: String) -> Result<(), Error> {`n" +
     "    AUTO_START_CANCELLED.store(true, AtomicOrdering::SeqCst);") `
    ("pub async fn start_app(app_handle: AppHandle, app_name: String) -> Result<(), Error> {`n" +
     "    if STARTUP_CHECK.try_lock().is_err() {`n" +
     "        info!(`"Start of '{}' asked during the update check; starting after it.`", app_name);`n" +
     "    }`n" +
     "    drop(STARTUP_CHECK.lock().await);`n" +
     "    AUTO_START_CANCELLED.store(true, AtomicOrdering::SeqCst);") `
    "start after the update check"

# GitHub refuses the launcher log as an attachment because it had no extension
# (app.2026-10-10, player report 2026-10-10). New logs are app.<date>.txt; the
# launcher never reads or deletes old logs, so app.<date> files just stay.
$loggerRs = Replace-Once $loggerRs `
    '        let file_appender = rolling::daily(&self.log_dir, &self.file_prefix);' `
    ("        let file_appender = rolling::RollingFileAppender::builder()`n" +
     "            .rotation(rolling::Rotation::DAILY)`n" +
     "            .filename_prefix(self.file_prefix.clone())`n" +
     "            .filename_suffix(`"txt`")`n" +
     "            .build(&self.log_dir)?;") `
    "name the launcher log app.<date>.txt"

# Hide the launcher window once the tool is seen running.
$appService = Replace-Once $appService `
    ("            emit_app().await;`n            return Ok(true);") `
    ("            emit_app().await;`n" +
     "            if let Some(window) = get_app_handle().and_then(|handle| handle.get_webview_window(`"main`")) {`n" +
     "                if let Err(e) = window.hide() {`n" +
     "                    warn!(`"Failed to hide main window after app '{}' started: {:?}`", app_name, e);`n" +
     "                }`n" +
     "            }`n" +
     "            return Ok(true);") `
    "hide the launcher once the tool runs"

# The auto start waited 10 s with nothing on screen, so players thought it did
# nothing (Leo 10-09): it now waits 5 s, says 「5 秒後自動啟動」 next to the
# switch with a 取消 button, then 「正在啟動…」 until the tool is up.
$appService = Replace-Once $appService `
    'info!("Scheduling auto-start for ''{}'' in 10 seconds.", app.name);' `
    ('info!("Scheduling auto-start for ''{}'' in 5 seconds.", app.name);' + "`n" + '                emitter::emit("auto_start_scheduled", 5u64);') `
    "announce the auto start"
$appService = Replace-Once $appService `
    'tokio::time::sleep(Duration::from_secs(10)).await;' `
    'tokio::time::sleep(Duration::from_secs(5)).await;' `
    "auto start after 5 s"
$appService = Replace-Once $appService `
    'pub(crate) async fn emit_app() {' `
    ("#[tauri::command]`n" +
     "pub async fn cancel_auto_start() -> Result<(), Error> {`n" +
     "    AUTO_START_CANCELLED.store(true, AtomicOrdering::SeqCst);`n" +
     "    info!(`"Delayed auto-start cancelled by the user.`");`n" +
     "    Ok(())`n" +
     "}`n`n" +
     'pub(crate) async fn emit_app() {') `
    "cancel command"
$libRs = Replace-Once $libRs `
    '    setup_app, start_app, stop_app, update_app_preferences, update_to_version, StartupOverrides,' `
    '    cancel_auto_start, setup_app, start_app, stop_app, update_app_preferences, update_to_version, StartupOverrides,' `
    "import the cancel command"
$libRs = Replace-Once $libRs `
    '                start_app,' `
    ("                start_app,`n                cancel_auto_start,") `
    "register the cancel command"

$appTsx = Replace-Once $appTsx `
    'const [startingAppName, setStartingAppName] = useState<string | null>(null);' `
    ('const [startingAppName, setStartingAppName] = useState<string | null>(null);' + "`n" +
     '    const [autoStartAt, setAutoStartAt] = useState<number | null>(null);' + "`n" +
     '    const [, setAutoStartTick] = useState(0);' + "`n" +
     '    useEffect(() => {' + "`n" +
     '        if (autoStartAt === null) return;' + "`n" +
     '        const timer = window.setInterval(() => setAutoStartTick(tick => tick + 1), 500);' + "`n" +
     '        return () => window.clearInterval(timer);' + "`n" +
     '    }, [autoStartAt]);') `
    "auto start countdown state"
$appTsx = Replace-Once $appTsx `
    'unlistenPromises.push(listen<App>("app", (event) => {' `
    ('unlistenPromises.push(listen<number>("auto_start_scheduled", (event) => {' + "`n" +
     '            setAutoStartAt(Date.now() + event.payload * 1000);' + "`n" +
     '        }));' + "`n" +
     '        unlistenPromises.push(listen<App>("app", (event) => {') `
    "auto start countdown listener"
$autoStartLabel = "{t('Auto Start')}</Typography>}`n" + (" " * 60) + "/>`n" + (" " * 56) + ")}"
$appTsx = Replace-Once $appTsx $autoStartLabel `
    ($autoStartLabel + "`n" +
     (" " * 56) + "{app.installed && !app.running && app.auto_start && autoStartAt !== null && autoStartAt > Date.now() - 30000 && (`n" +
     (" " * 60) + "<Typography variant=`"body2`" color=`"primary`" sx={{fontWeight: 600, ml: 1}}>`n" +
     (" " * 64) + "{autoStartAt > Date.now() ? t('autoStartIn', {n: Math.ceil((autoStartAt - Date.now()) / 1000)}) : t('autoStarting')}`n" +
     (" " * 60) + "</Typography>`n" +
     (" " * 56) + ")}`n" +
     (" " * 56) + "{app.installed && !app.running && app.auto_start && autoStartAt !== null && autoStartAt > Date.now() && (`n" +
     (" " * 60) + "<Button size=`"small`" variant=`"outlined`" color=`"warning`" sx={{ml: 1}} onClick={() => { invoke('cancel_auto_start').catch(() => {}); setAutoStartAt(null); }}>{t('Cancel')}</Button>`n" +
     (" " * 56) + ")}") `
    "auto start countdown and cancel"
foreach ($entry in @(
    @("Auto Start", "Auto-starting in {{n}} s", "Starting..."),
    @("自动启动", "{{n}} 秒后自动启动", "正在启动…"),
    @("自動啟動", "{{n}} 秒後自動啟動", "正在啟動…"),
    @("自動起動", "{{n}} 秒後に自動起動", "起動中…"),
    @("자동 시작", "{{n}}초 후 자동 시작", "시작 중…"),
    @("Inicio Automático", "Inicio automático en {{n}} s", "Iniciando...")
)) {
    $line = '"Auto Start": "' + $entry[0] + '"'
    $i18n = Replace-Once $i18n $line `
        ($line + ",`n            `"autoStartIn`": `"" + $entry[1] + "`",`n            `"autoStarting`": `"" + $entry[2] + "`"") `
        ("auto start text " + $entry[0])
}

# Try the package install again when a download breaks off (player report
# 2026-10-14: PySide6 from the Aliyun mirror stopped at 34.6/72.4 MB with a
# urllib3 read error, and older pip does not resume a broken download). Up
# to 3 tries; pip's cache keeps every package already downloaded, and the
# last try uses the other China mirror when Aliyun or Tsinghua is set. If
# all fail, the message says what the player can do.
$pythonEnvRs = Replace-Once $pythonEnvRs `
    (@'
#[cfg(target_os = "windows")]
pub async fn install_requirements(
    app_name: &str,
    requirements: &str,
    project_dir: &Path,
    pip_args: &str,
) -> Result<(), Error> {
    let python_exe = get_python_exe(app_name, false);
'@ -replace "`r`n", "`n") `
    (@'
#[cfg(target_os = "windows")]
const PIP_INSTALL_ATTEMPTS: usize = 3;

/// The other China mirror for the last try when the configured one keeps
/// breaking off downloads; None keeps the configured source.
#[cfg(target_os = "windows")]
fn fallback_pip_index_url() -> Option<String> {
    let configured = GLOBAL_CONFIG_STATE
        .get()?
        .lock()
        .ok()?
        .get_effective_pip_index_url()?;
    if configured.contains("aliyun") {
        Some("https://pypi.tuna.tsinghua.edu.cn/simple".to_string())
    } else if configured.contains("tsinghua") {
        Some("https://mirrors.aliyun.com/pypi/simple/".to_string())
    } else {
        None
    }
}

#[cfg(target_os = "windows")]
pub async fn install_requirements(
    app_name: &str,
    requirements: &str,
    project_dir: &Path,
    pip_args: &str,
) -> Result<(), Error> {
    let mut last_error = String::new();
    for attempt in 1..=PIP_INSTALL_ATTEMPTS {
        let index_override = if attempt == PIP_INSTALL_ATTEMPTS {
            fallback_pip_index_url()
        } else {
            None
        };
        if attempt > 1 {
            emit_info!(
                app_name,
                "Package download broke off; trying again ({}/{}){}. Packages already downloaded are kept.",
                attempt,
                PIP_INSTALL_ATTEMPTS,
                index_override
                    .as_deref()
                    .map(|url| format!(" from {}", url))
                    .unwrap_or_default()
            );
        }
        match install_requirements_once(
            app_name,
            requirements,
            project_dir,
            pip_args,
            index_override.as_deref(),
        )
        .await
        {
            Ok(()) => return Ok(()),
            Err(e) => {
                warn!(
                    "pip install for '{}' failed (attempt {}/{}): {}",
                    app_name, attempt, PIP_INSTALL_ATTEMPTS, e
                );
                last_error = e.to_string();
            }
        }
    }
    Err(err!(
        "安装所需套件失败（试了 {} 次，多半是下载中途断线）：请检查网络，或在启动器「设置」把 pip 来源换成别的，再按一次安装，已下载的套件会保留。Installing packages failed {} times, most likely the download broke off: check the network or pick another pip source in Settings, then press install again. ({})",
        PIP_INSTALL_ATTEMPTS,
        PIP_INSTALL_ATTEMPTS,
        last_error
    ))
}

#[cfg(target_os = "windows")]
async fn install_requirements_once(
    app_name: &str,
    requirements: &str,
    project_dir: &Path,
    pip_args: &str,
    index_override: Option<&str>,
) -> Result<(), Error> {
    let python_exe = get_python_exe(app_name, false);
'@ -replace "`r`n", "`n") `
    "retry the package install"
$pythonEnvRs = Replace-Once $pythonEnvRs `
    (@'
        let index_url = config.get_effective_pip_index_url();
'@ -replace "`r`n", "`n") `
    (@'
        let index_url = index_override
            .map(str::to_string)
            .or_else(|| config.get_effective_pip_index_url());
'@ -replace "`r`n", "`n") `
    "use the other mirror on the last try"

Set-Content -LiteralPath $appServicePath -Value $appService -Encoding UTF8
Set-Content -LiteralPath $pythonEnvRsPath -Value $pythonEnvRs -Encoding UTF8
Set-Content -LiteralPath $libRsPath -Value $libRs -Encoding UTF8
Set-Content -LiteralPath $gitRsPath -Value $gitRs -Encoding UTF8
Set-Content -LiteralPath $loggerRsPath -Value $loggerRs -Encoding UTF8
Set-Content -LiteralPath $appTsxPath -Value $appTsx -Encoding UTF8
Set-Content -LiteralPath $i18nPath -Value $i18n -Encoding UTF8

Update-InstallerNsiTemplate -BuildDirPath $buildPath

pnpm install --dir $buildPath
if ($SkipBuild) {
    Write-Host "PyAppify source prepared without compiling the launcher."
} else {
    pnpm --dir $buildPath exec cargo fmt --manifest-path (Join-Path $buildPath "src-tauri\Cargo.toml")
    pnpm --dir $buildPath tauri build
}
