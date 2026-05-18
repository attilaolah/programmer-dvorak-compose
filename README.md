# programmer-dvorak-compose

Fork of Roland Kaufmann's macOS DVP keyboard layout, with additional compose key sequences.

The layout currently adds Hungarian double acute compose sequences:

- `=o` -> `ő`
- `=O` -> `Ő`
- `=u` -> `ű`
- `=U` -> `Ű`

## Nix

This flake exposes:

- `packages.${system}.default`: the four keyboard layout files with snake_case store paths.
- `overlays.default`: adds `pkgs."programmer-dvorak-compose"`.
- `homeManagerModules.default`: installs the macOS bundle under `~/Library/Keyboard Layouts`.

The Home Manager entries are guarded with `pkgs.stdenv.isDarwin` and install the bundle as real directories with per-file symlinks.

Example:

```nix
{
  inputs.programmer-dvorak-compose.url = "git+file:///Users/olaa/repos/my/programmer-dvorak-compose";

  outputs = inputs @ {
    programmer-dvorak-compose,
    ...
  }: {
    homeConfigurations.example = home-manager.lib.homeManagerConfiguration {
      modules = [
        programmer-dvorak-compose.homeManagerModules.default
      ];
    };
  };
}
```
