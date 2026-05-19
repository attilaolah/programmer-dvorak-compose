{
  fetchurl,
  libx11,
  lib,
  python314,
  libicns,
  librsvg,
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
      libicns
      librsvg
      python314
    ];

    dontConfigure = true;

    buildPhase = ''
      runHook preBuild

      python3.14 scripts/generate_keylayout.py \
        --programmer-dvorak-pkg ${programmerDvorakPkg} \
        --libx11-src ${libx11.src} \
        --output programmer_dvorak_compose.keylayout

      mkdir KeyboardAlt.iconset
      sed 's/fill="currentColor"/fill="#fff"/' resources/keyboard_alt.svg > KeyboardAlt.svg
      rsvg-convert -w 16 -h 16 KeyboardAlt.svg -o KeyboardAlt.iconset/icon_16x16.png
      rsvg-convert -w 32 -h 32 KeyboardAlt.svg -o KeyboardAlt.iconset/icon_32x32.png
      rsvg-convert -w 64 -h 64 KeyboardAlt.svg -o KeyboardAlt.iconset/icon_32x32@2x.png
      rsvg-convert -w 128 -h 128 KeyboardAlt.svg -o KeyboardAlt.iconset/icon_128x128.png
      rsvg-convert -w 256 -h 256 KeyboardAlt.svg -o KeyboardAlt.iconset/icon_128x128@2x.png
      png2icns "Programmer Dvorak Compose.icns" \
        KeyboardAlt.iconset/icon_16x16.png \
        KeyboardAlt.iconset/icon_32x32.png \
        KeyboardAlt.iconset/icon_32x32@2x.png \
        KeyboardAlt.iconset/icon_128x128.png \
        KeyboardAlt.iconset/icon_128x128@2x.png

      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall

      bundle="$out/Library/Keyboard Layouts/Programmer Dvorak Compose.bundle"
      install -Dm0644 ${infoPlist} "$bundle/Contents/Info.plist"
      install -Dm0644 ${versionPlist} "$bundle/Contents/version.plist"
      install -Dm0644 resources/english.lproj/info_plist.strings "$bundle/Contents/Resources/English.lproj/InfoPlist.strings"
      install -Dm0644 programmer_dvorak_compose.keylayout "$bundle/Contents/Resources/Programmer Dvorak Compose.keylayout"
      install -Dm0644 "Programmer Dvorak Compose.icns" "$bundle/Contents/Resources/Programmer Dvorak Compose.icns"

      runHook postInstall
    '';

    meta = {
      description = "Programmer Dvorak keyboard layout with extra compose sequences";
      license = lib.licenses.mit;
      platforms = lib.platforms.unix;
    };
  }
