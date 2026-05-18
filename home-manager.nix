self: {
  lib,
  pkgs,
  ...
}: let
  package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
in {
  home.file = lib.optionalAttrs pkgs.stdenv.isDarwin {
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Info.plist".source = "${package}/info.plist";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/version.plist".source = "${package}/version.plist";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Resources/English.lproj/InfoPlist.strings".source = "${package}/info_plist.strings";
    "Library/Keyboard Layouts/Programmer Dvorak Compose.bundle/Contents/Resources/Programmer Dvorak Compose.keylayout".source = "${package}/programmer_dvorak_compose.keylayout";
  };
}
