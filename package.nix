{
  lib,
  stdenvNoCC,
}:
stdenvNoCC.mkDerivation {
  pname = "programmer-dvorak-compose";
  version = "1.2.1";

  src = ./.;

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    install -Dm0644 info.plist "$out/info.plist"
    install -Dm0644 version.plist "$out/version.plist"
    install -Dm0644 resources/english.lproj/info_plist.strings "$out/info_plist.strings"
    install -Dm0644 resources/programmer_dvorak_compose.keylayout "$out/programmer_dvorak_compose.keylayout"

    runHook postInstall
  '';

  meta = {
    description = "Programmer Dvorak keyboard layout with extra compose sequences";
    license = lib.licenses.mit;
    platforms = lib.platforms.darwin;
  };
}
