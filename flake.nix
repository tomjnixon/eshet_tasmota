{
  description = "eshet.py misc";

  inputs = {
    utils.url = "github:numtide/flake-utils";
    eshetpy.url = "github:tomjnixon/eshet.py/main";
    eshetpy.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, utils, eshetpy }:
    utils.lib.eachSystem utils.lib.defaultSystems (system:
      let
        pkgs = nixpkgs.legacyPackages."${system}";
        python = pkgs.python3;
      in
      rec {
        packages.eshetpy = eshetpy.packages."${system}".eshet_py;

        packages.eshet_tasmota = python.pkgs.buildPythonApplication {
          name = "eshet_tasmota";
          src = ./.;
          pyproject = true;
          propagatedBuildInputs = [
            packages.eshetpy
            python.pkgs.aiomqtt
          ];
          nativeBuildInputs = [
            python.pkgs.setuptools
          ];
        };

        packages.default = packages.eshet_tasmota;

        devShells.eshet_tasmota = packages.eshet_tasmota.overridePythonAttrs (a: {
          nativeBuildInputs = a.nativeBuildInputs ++ [
            python.pkgs.black
            pkgs.nixpkgs-fmt
            python.pkgs.venvShellHook
          ];
          venvDir = "./venv";
          postShellHook = ''
            python -m pip install -e .
          '';
        });
        devShells.default = devShells.eshet_tasmota;
      }
    );
}

