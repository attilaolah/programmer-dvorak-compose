self: {
  lib,
  pkgs,
  ...
}: {
  config = lib.mkIf pkgs.stdenv.isDarwin (let
    package = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
  in {
    system.activationScripts.programmer-dvorak-compose.text = ''
      set -eu

      src="${package}/Library/Keyboard Layouts/Programmer Dvorak Compose.bundle"
      dst="/Library/Keyboard Layouts/Programmer Dvorak Compose.bundle"
      tmp="/Library/Keyboard Layouts/.Programmer Dvorak Compose.bundle.tmp.$$"

      rm -rf "$tmp"
      mkdir -p "$tmp/Contents/Resources/English.lproj"

      install -m 0644 "$src/Contents/Info.plist" "$tmp/Contents/Info.plist"
      install -m 0644 "$src/Contents/version.plist" "$tmp/Contents/version.plist"
      install -m 0644 "$src/Contents/Resources/English.lproj/InfoPlist.strings" "$tmp/Contents/Resources/English.lproj/InfoPlist.strings"
      install -m 0644 "$src/Contents/Resources/Programmer Dvorak Compose.keylayout" "$tmp/Contents/Resources/Programmer Dvorak Compose.keylayout"
      install -m 0644 "$src/Contents/Resources/Programmer Dvorak Compose.icns" "$tmp/Contents/Resources/Programmer Dvorak Compose.icns"

      chown -R root:wheel "$tmp"
      chmod -R u=rwX,go=rX "$tmp"

      if command -v xattr >/dev/null 2>&1; then
        xattr -cr "$tmp"
      fi

      rm -rf "$dst"
      mv "$tmp" "$dst"
    '';
  });
}
