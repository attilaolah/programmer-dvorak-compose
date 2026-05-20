# Programmer Dvorak Compose ⌨️

> Fork of Roland Kaufmann's macOS DVP keyboard layout, with Linux-style compose key sequences.

<img width="359" height="122" alt="Screenshot showcasing the icon in the menu bar"
  src="https://github.com/user-attachments/assets/4dd70f65-2eba-4597-ac90-2c38b3c389a4" />

---

The packaged `.keylayout` is generated at build time from:

- Roland Kaufmann's original Programmer Dvorak macOS package.
- libX11's `en_US.UTF-8/Compose.pre`, which is the default Compose table used by X11 on Linux.

The generator keeps the original DVP key maps, promotes printable key outputs into macOS keylayout actions, and emits
the representable `Multi_key` compose sequences from the X11 source.

The resulting compose key sequences contain all the good stuff, including:

- Full set of German, Hungarian, Serbian (Latin) characters, including ä, ő, ű, í, đ, ž, etc.
- Less common punctuations like —, –, ·, ←, →, ≤, ≥, ⇐, ⇒, «, », “, ”, …
- 🖖 ([`LLAP`](https://en.wikipedia.org/wiki/Vulcan_salute)), 💩 (`poo`) and a few other gems.

## ❄️ Nix: Home Manager + nix-darwin integration

This flake exposes:

- `packages.${system}.default`: a complete `Library/Keyboard Layouts/Programmer Dvorak Compose.bundle` tree that can be
  copied into `/Library` or `~/Library`.
- `overlays.default`: adds `pkgs."programmer-dvorak-compose"`.
- `homeManagerModules.default`: installs the macOS bundle under `~/Library/Keyboard Layouts`.
- `darwinModules.default`: installs the macOS bundle globally under `/Library/Keyboard Layouts`.

The Home Manager entries are guarded with `pkgs.stdenv.isDarwin` and install the bundle as real directories with
per-file symlinks. The nix-darwin module installs the global bundle during activation by copying the Nix store files
into a real bundle. This avoids per-file symlinks, which macOS may not discover for global keyboard layouts.

Example:

```nix
{
  inputs.programmer-dvorak-compose.url = "github:attilaolah/programmer-dvorak-compose";

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

For a global install through nix-darwin:

```nix
{
  inputs.programmer-dvorak-compose.url = "github:attilaolah/programmer-dvorak-compose";

  outputs = inputs @ {
    programmer-dvorak-compose,
    ...
  }: {
    darwinConfigurations.example = nix-darwin.lib.darwinSystem {
      modules = [
        programmer-dvorak-compose.darwinModules.default
      ];
    };
  };
}
```
