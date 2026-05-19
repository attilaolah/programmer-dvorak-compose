{
  description = "Programmer Dvorak keyboard layout with extra compose sequences";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    systems = [
      "aarch64-linux"
      "aarch64-darwin"
      "x86_64-linux"
      "x86_64-darwin"
    ];

    forAllSystems = function:
      nixpkgs.lib.genAttrs systems (system:
        function (import nixpkgs {
          inherit system;
        }));
  in {
    overlays.default = final: prev: {
      "programmer-dvorak-compose" = final.callPackage ./package.nix {};
    };

    packages = forAllSystems (pkgs: let
      package = pkgs.callPackage ./package.nix {};
    in {
      "programmer-dvorak-compose" = package;
      default = package;
    });

    devShells = forAllSystems (pkgs: {
      default = pkgs.mkShellNoCC {
        packages = with pkgs; [
          alejandra
          libplist
          prettier
          pyright
          ruff
          ty
          (python314.withPackages (ps:
            with ps; [
              defusedxml
              pytest
              pyupgrade
              yamllint
            ]))
        ];
      };
    });

    homeManagerModules = {
      default = import ./home-manager.nix self;
      programmer-dvorak-compose = self.homeManagerModules.default;
    };
  };
}
