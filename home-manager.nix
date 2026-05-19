self: {
  lib,
  pkgs,
  ...
}: {
  home.file = lib.optionalAttrs pkgs.stdenv.isDarwin (let
    package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
    bundle = "${package}/Library/Keyboard Layouts/Programmer Dvorak Compose.bundle";
  in {
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Info.plist".source = "${bundle}/Contents/Info.plist";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/version.plist".source = "${bundle}/Contents/version.plist";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Resources/English.lproj/InfoPlist.strings".source = "${bundle}/Contents/Resources/English.lproj/InfoPlist.strings";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Resources/Programmer Dvorak Compose.keylayout".source = "${bundle}/Contents/Resources/Programmer Dvorak Compose.keylayout";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Resources/Programmer Dvorak Compose.icns".source = "${bundle}/Contents/Resources/Programmer Dvorak Compose.icns";
  });
}
