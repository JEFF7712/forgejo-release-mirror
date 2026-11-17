flake:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.forgejo-release-mirror;
  repository = lib.types.strMatching "[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+";
in
{
  options.services.forgejo-release-mirror = {
    enable = lib.mkEnableOption "verified Forgejo to GitHub release mirroring";
    package = lib.mkOption {
      type = lib.types.package;
      default = flake.packages.${pkgs.stdenv.hostPlatform.system}.default;
      description = "Release mirror executable package.";
    };
    forgejoOrigin = lib.mkOption {
      type = lib.types.str;
      description = "Forgejo scheme and host, including a port if needed.";
    };
    sourceRepository = lib.mkOption {
      type = repository;
      description = "Forgejo owner/repository to read.";
    };
    destinationRepository = lib.mkOption {
      type = repository;
      default = cfg.sourceRepository;
      defaultText = lib.literalExpression "config.services.forgejo-release-mirror.sourceRepository";
      description = "GitHub owner/repository to update.";
    };
    minimumVersion = lib.mkOption {
      type = lib.types.str;
      description = "Oldest version tag to manage.";
    };
    environmentFile = lib.mkOption {
      type = lib.types.strMatching "/.*";
      description = "Runtime file containing FORGEJO_READ_TOKEN and GITHUB_TOKEN. Keep it outside the Nix store.";
    };
    onCalendar = lib.mkOption {
      type = lib.types.str;
      default = "*:0/5";
      description = "Systemd calendar expression for synchronization.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.forgejo-release-mirror = {
      description = "Mirror verified Forgejo releases to GitHub";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.escapeShellArgs [
          (lib.getExe cfg.package)
          "--forgejo-origin"
          cfg.forgejoOrigin
          "--source-repository"
          cfg.sourceRepository
          "--destination-repository"
          cfg.destinationRepository
          "--minimum-version"
          cfg.minimumVersion
        ];
        EnvironmentFile = cfg.environmentFile;
        TimeoutStartSec = "15min";
        DynamicUser = true;
        UMask = "0077";
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
        ];
      };
    };
    systemd.timers.forgejo-release-mirror = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = cfg.onCalendar;
        RandomizedDelaySec = "30s";
        Persistent = true;
      };
    };
  };
}
