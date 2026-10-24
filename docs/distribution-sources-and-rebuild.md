# Source access and modified-library rebuilding / Kaynak ve yeniden derleme

QR Scanner's own code is MIT licensed. Third-party code keeps its own license.
You may modify the LGPL-covered library and reverse-engineer the combined
application to debug those modifications; no additional project restriction
is imposed. This document provides the source/recombination route used for
the single-file Windows distribution, rather than claiming a runtime shared
library replacement mechanism.

## Included material

- `APPLICATION_SOURCE.zip`: complete tracked application source at the exact
  commit in `SOURCE_REVISION.txt`, including build recipes, requirements,
  project assets and these instructions. Extract into a separate directory.
- `THIRD_PARTY_LICENSES/SOURCES/pystray-0.19.5.tar.gz`: full upstream source
  (LGPL-3.0-or-later), immutable upstream commit recorded in manifest.json.
- `THIRD_PARTY_LICENSES/SOURCES/certifi-2026.7.22.tar.gz`: original certifi
  source, including the CA certificate source form, under MPL-2.0.
- `THIRD_PARTY_LICENSES/SOURCES/MPL-2.0.txt`: full MPL text.
- `THIRD_PARTY_LICENSES/DEPENDENCY_INVENTORY.json`: actual frozen Python
  distributions; corresponding license trees are in `INVENTORY_LICENSES`.
- All upstream archive digests/URLs are in `SOURCES/manifest.json` and are
  verified during packaging. No download or account is needed to obtain the
  included application, pystray or certifi source.

## Build an interface-compatible modified pystray

Use a Windows x64 system and Python 3.12.x (the release baseline is 3.12.14).
Python and build dependencies may be obtained from their official sources;
the pinned Python packages below require internet access to install.
This is source rebuilding, not a claim of byte-for-byte reproducible EXEs.

1. Extract `APPLICATION_SOURCE.zip` to a new folder and open PowerShell there.
2. Create an isolated environment and install the pinned requirements:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

3. Extract the included pystray archive into another folder. Its Python package
   is `lib/pystray`. Modify those source files while preserving their copyright
   and license headers. Keep the API used by `tray_app.py` compatible.
4. Point the build to the folder containing your modified `pystray` directory:

   ```powershell
   $env:WQRS_BUILD_IMPORT_PATH = 'C:\path\to\extracted-pystray\lib'
   .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath build\modified-dist --workpath build\modified-work packaging\QR-Scanner.spec
   Remove-Item Env:\WQRS_BUILD_IMPORT_PATH
   $probe = Start-Process -FilePath .\build\modified-dist\QR-Scanner.exe -ArgumentList '--self-test' -WindowStyle Hidden -PassThru -Wait
   $probe.ExitCode
   ```

5. Exit any running original QR Scanner using its tray Exit action, then open
   your rebuilt EXE. It needs no project signing key, activation, bypass secret
   or embedded account credential. Existing OS-user pairing storage remains
   separate from the executable. Test tray actions and Phone-to-PC as well as
   your modified library's behavior. Redistribute modifications under the
   applicable upstream license and supply their corresponding source.

Do not set `WQRS_REBUILD_PROBE` for ordinary builds. It is reserved for our
validation build, which adds a harmless library marker and asserts at startup
that the modified code was actually imported.

The frozen Windows package excludes the separate `opencv_videoio_ffmpeg*.dll`
plugin: the app scans local camera indices using Media Foundation/DirectShow,
and does not expose video-file/network-stream scanning. OpenCV itself and
its image codecs remain. OpenCV/NumPy upstream notices include native
subcomponent licenses and the GCC runtime exception; do not discard them.

## Türkçe kısa açıklama

MIT lisansı korunur; uygulama ücretsiz kullanılabilir, paylaşılabilir ve
geliştirilebilir. LGPL bileşenlerin kendi hakları korunur. Kaynak kodlar
paketin içinde bulunur; değiştirilmiş pystray ile yeni EXE oluşturmak için
yukarıdaki adımları uygulayın. Normal kullanıcıların yeniden derleme yapması
gerekmez. Bu yönerge teknik dağıtım desteğidir, hukuki uygunluk belgesi değildir.
