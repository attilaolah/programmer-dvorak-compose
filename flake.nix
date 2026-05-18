{
  description = "Programmer Dvorak keyboard layout with extra compose sequences";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    systems = [
      "aarch64-darwin"
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

    homeManagerModules.default = import ./home-manager.nix self;
    homeManagerModules.programmer-dvorak-compose = self.homeManagerModules.default;
  };
}
