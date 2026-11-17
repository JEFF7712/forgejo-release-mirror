{
  description = "Verified Forgejo to GitHub release mirroring";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.python3Packages.buildPythonApplication {
            pname = "forgejo-release-mirror";
            version = "0.1.0";
            pyproject = true;
            src = self;
            build-system = [ pkgs.python3Packages.setuptools ];
            checkPhase = ''
              runHook preCheck
              python -m unittest discover -s tests -v
              runHook postCheck
            '';
            pythonImportsCheck = [ "forgejo_release_mirror" ];
            meta = {
              description = "Mirror published Forgejo releases and verified assets to GitHub";
              license = pkgs.lib.licenses.mit;
              mainProgram = "forgejo-release-mirror";
              platforms = pkgs.lib.platforms.unix;
            };
          };
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/forgejo-release-mirror";
          meta.description = "Mirror published Forgejo releases to GitHub";
        };
      });

      checks = forAllSystems (system: {
        package = self.packages.${system}.default;
      });

      formatter = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        pkgs.writeShellApplication {
          name = "format-nix";
          runtimeInputs = [ pkgs.nixfmt ];
          text = ''
            exec nixfmt flake.nix nix/module.nix "$@"
          '';
        }
      );

      nixosModules.default = import ./nix/module.nix self;
    };
}
