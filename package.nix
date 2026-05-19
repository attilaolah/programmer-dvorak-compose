{
  fetchurl,
  libx11,
  lib,
  python314,
  stdenvNoCC,
  replaceVars,
  version ? (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version,
}: let
  infoPlist = replaceVars ./info.plist {
    inherit version;
  };
  versionPlist = replaceVars ./version.plist {
    inherit version;
  };
  programmerDvorakPkg = fetchurl {
    urls = [
      "https://www.kaufmann.no/downloads/macos/ProgrammerDvorak-1_2_13.pkg.zip"
      "https://ipfs.io/ipfs/bafkreieef75poffkvsi3akd4jzcxn4ml4g74gjutockzhiiyk4vhzr4aay"
      "https://dweb.link/ipfs/bafkreieef75poffkvsi3akd4jzcxn4ml4g74gjutockzhiiyk4vhzr4aay"
    ];
    hash = "sha256-hC/69xSqrJGwKHxORXbxi+G/wyaTcJWToRhXKnzHgAY=";
  };
in
  stdenvNoCC.mkDerivation {
    pname = "programmer-dvorak-compose";
    inherit version;

    src = ./.;

    nativeBuildInputs = [
      python314
    ];

    dontConfigure = true;

    buildPhase = ''
      runHook preBuild

      python3.14 scripts/generate_keylayout.py \
        --programmer-dvorak-pkg ${programmerDvorakPkg} \
        --libx11-src ${libx11.src} \
        --output programmer_dvorak_compose.keylayout

      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall

      install -Dm0644 ${infoPlist} "$out/info.plist"
      install -Dm0644 ${versionPlist} "$out/version.plist"
      install -Dm0644 resources/english.lproj/info_plist.strings "$out/info_plist.strings"
      install -Dm0644 programmer_dvorak_compose.keylayout "$out/programmer_dvorak_compose.keylayout"

      runHook postInstall
    '';

    meta = {
      description = "Programmer Dvorak keyboard layout with extra compose sequences";
      license = lib.licenses.mit;
      platforms = lib.platforms.unix;
    };
  }
