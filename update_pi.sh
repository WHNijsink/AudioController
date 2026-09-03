#!/bin/bash
# update_pi.sh - AudioController op een van de Pi's bijwerken/beheren vanaf deze checkout.
# Update volgt README stap 3 (rsync i.p.v. scp) en stap 4 (service herstarten/herinstalleren).
# LET OP: bevat interne deploy-details (hostnames/IP/poort/users) van de gergem-locaties.
# Alleen op de eigen fork bewaren; niet naar de publieke upstream (ArjenGuis) pushen.
#
# Gebruik:
#   ./update_pi.sh                     menu: kies locatie en actie
#   ./update_pi.sh west                kies locatie direct (noord|zuid|west|wierden)
#   ./update_pi.sh west --dry-run      alleen tonen wat er zou wijzigen (verandert niets)
#   ./update_pi.sh west --yes          updaten zonder bevestigingsvraag
#   ./update_pi.sh west --no-restart   updaten maar service niet herstarten
#   ./update_pi.sh west --full         volledige deploy: alle bestanden + systemd-unit (her)installeren
#   ./update_pi.sh west --backup       alleen backup: download de huidige Pi-bestanden naar een lokaal mapje
#   ./update_pi.sh west --no-backup    sla de automatische pre-deploy backup over
#   ./update_pi.sh west --health       snelle HTTP-healthcheck (wijzigt niets)
#   ./update_pi.sh west --status       software/systeem-status van de Pi (wijzigt niets)
#   ./update_pi.sh west --logs         laatste service-logregels (wijzigt niets)
#   ./update_pi.sh west --restart      alleen de service herstarten (geen sync)
#
# KEY=/pad/naar/key    overschrijft de ssh-key (standaard ~/.ssh/rpi_ed25519).
# BACKUP_DIR=/pad      overschrijft de backup-map (standaard ~/AudioController_pi_backups).
# KEEP_BACKUPS=N       houd alleen de N nieuwste backups per locatie (standaard 0 = alles bewaren).
#
# Backup: update en volledige deploy downloaden ALTIJD eerst de huidige Pi-bestanden
# naar $BACKUP_DIR/<locatie>/<datum-tijd>/ voordat er iets wordt overschreven (te
# omzeilen met --no-backup). Elke backup krijgt een eigen datum-tijd-submap, dus ze
# stapelen en je houdt er meerdere. --backup doet alleen dat downloaden, zonder te pushen.
#
# Wat wordt gesynct (README stap 3):
#   ./audio_controller          -> ~/AudioController   (de package, incl. gecompileerde main.js)
#   ./run_audio_controller.sh   -> ~/AudioController
#   ./audio_controller.service  -> ~/AudioController    (alleen geactiveerd bij --full)
#   ./audio_controller.html     -> ~/Desktop            (kiosk-launcher)
# Niet meegesynct: vendored assets (bootstrap*/fontawesome*) - die staan al op de Pi en
# wijzigen niet; en *.pyc/__pycache__/.pytest_cache/.DS_Store.
set -eo pipefail
cd "$(dirname "$0")"

KEY="${KEY:-$HOME/.ssh/rpi_ed25519}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/AudioController_pi_backups}"
KEEP_BACKUPS="${KEEP_BACKUPS:-0}"   # 0 = alle backups bewaren; >0 = alleen de N nieuwste houden
SERVICE=audio_controller.service
REMOTE_APP="~/AudioController/audio_controller/audio_controller"
LOCATIES=(noord zuid west wierden)

host_for() {
    case "$1" in
        noord)   echo "noord.gergemrijssen.nl" ;;
        zuid)    echo "zuid.gergemrijssen.nl" ;;
        west)    echo "west.gergemrijssen.nl" ;;
        wierden) echo "194.122.241.158" ;;
    esac
}
user_for() {
    case "$1" in
        wierden) echo "gergemwierden" ;;
        *)       echo "pi" ;;
    esac
}
port_for() {
    echo "2222"
}

if [ -t 1 ]; then
    BOLD=$(tput bold); DIM=$(tput dim); RESET=$(tput sgr0)
else
    BOLD=""; DIM=""; RESET=""
fi

# --- argumenten ---
LOC=""
ACTIE=""        # update | full | backup | health | status | logs | restart
DRY_RUN=""
RESTART=1
ASSUME_YES=0
DO_BACKUP=1     # update/full downloaden altijd eerst de huidige Pi-bestanden
for arg in "$@"; do
    case "$arg" in
        --dry-run)    ACTIE="update"; DRY_RUN="-n" ;;
        --no-restart) ACTIE="update"; RESTART=0 ;;
        --no-backup)  DO_BACKUP=0 ;;
        --yes)        [ -z "$ACTIE" ] && ACTIE="update"; ASSUME_YES=1 ;;
        --full)       ACTIE="full" ;;
        --backup)     ACTIE="backup" ;;
        --health)     ACTIE="health" ;;
        --status)     ACTIE="status" ;;
        --logs)       ACTIE="logs" ;;
        --restart)    ACTIE="restart" ;;
        noord|zuid|west|wierden)             LOC="$arg" ;;
        pi-noord|pi-zuid|pi-west|pi-wierden) LOC="${arg#pi-}" ;;
        *) echo "Onbekende optie: $arg (zie kop van dit script)"; exit 2 ;;
    esac
done

# --- locatie kiezen ---
if [ -z "$LOC" ]; then
    [ -t 0 ] || { echo "Geen locatie opgegeven en geen terminal voor het menu."; exit 2; }
    echo "${BOLD}AudioController beheer${RESET}"
    echo
    echo "${BOLD}Kies locatie:${RESET}"
    i=1
    for l in "${LOCATIES[@]}"; do
        printf "  %d) %-8s %s%s@%s:%s%s\n" "$i" "$l" "$DIM" "$(user_for "$l")" "$(host_for "$l")" "$(port_for "$l")" "$RESET"
        i=$((i + 1))
    done
    echo "  q) stoppen"
    while true; do
        read -r -p "Keuze [1-${#LOCATIES[@]}, q]: " k
        case "$k" in
            [1-9])
                if [ "$k" -le "${#LOCATIES[@]}" ]; then
                    LOC="${LOCATIES[$((k - 1))]}"
                    break
                fi ;;
            q|Q) echo "Gestopt."; exit 0 ;;
        esac
    done
fi

PI_HOST=$(host_for "$LOC")
PI_USER=$(user_for "$LOC")
PI_PORT=$(port_for "$LOC")
DOEL="$PI_USER@$PI_HOST (poort $PI_PORT)"
SSH=(ssh -i "$KEY" -p "$PI_PORT" -o ConnectTimeout=10 "$PI_USER@$PI_HOST")

# --- actie kiezen ---
if [ -z "$ACTIE" ]; then
    if [ -t 0 ]; then
        echo
        echo "${BOLD}Actie voor $LOC${RESET} ${DIM}$DOEL${RESET}"
        echo "  1) update             ${DIM}backup + sync alle bestanden + service-herstart${RESET}"
        echo "  2) dry-run            ${DIM}toon wat update zou wijzigen, verandert niets${RESET}"
        echo "  3) update zonder herstart"
        echo "  4) volledige deploy   ${DIM}backup + alles + systemd-unit (her)installeren (stap 4)${RESET}"
        echo "  5) backup             ${DIM}download huidige Pi-bestanden lokaal, zonder te pushen${RESET}"
        echo "  6) healthcheck        ${DIM}snelle HTTP-check, wijzigt niets${RESET}"
        echo "  7) status             ${DIM}versie, service, uptime, schijf, temperatuur${RESET}"
        echo "  8) logs               ${DIM}laatste 40 regels van de service${RESET}"
        echo "  9) herstart service   ${DIM}geen sync, alleen systemctl restart${RESET}"
        echo "  q) stoppen"
        while true; do
            read -r -p "Keuze [1-9, q]: " k
            case "$k" in
                1) ACTIE="update"; break ;;
                2) ACTIE="update"; DRY_RUN="-n"; break ;;
                3) ACTIE="update"; RESTART=0; break ;;
                4) ACTIE="full"; break ;;
                5) ACTIE="backup"; break ;;
                6) ACTIE="health"; break ;;
                7) ACTIE="status"; break ;;
                8) ACTIE="logs"; break ;;
                9) ACTIE="restart"; break ;;
                q|Q) echo "Gestopt."; exit 0 ;;
            esac
        done
    else
        ACTIE="update"
    fi
fi

healthcheck() {
    local code_root code_bord
    code_root=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$PI_HOST:8080/" || echo 000)
    code_bord=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://$PI_HOST:8080/psalmbord" || echo 000)
    echo "http://$PI_HOST:8080/          -> $code_root  (verwacht: 200; 000 = niet bereikbaar vanaf hier)"
    echo "http://$PI_HOST:8080/psalmbord -> $code_bord  (302 = login actief, nieuw gedrag; 200 = oude versie draait nog)"
}

bevestig() {
    if [ "$ASSUME_YES" -eq 0 ]; then
        read -r -p "$1 [j/N] " antwoord
        case "$antwoord" in
            j|J|ja|y|Y) ;;
            *) echo "Afgebroken."; exit 0 ;;
        esac
    fi
}

preflight() {
    if ! ls audio_controller/audio_controller/static/js/main*.js >/dev/null 2>&1; then
        echo "FOUT: geen gecompileerde frontend (static/js/main*.js ontbreekt)."
        echo "Compileer eerst: python -m manage_env compile_on_save (zie README)."
        exit 1
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "LET OP: working tree bevat niet-gecommitte wijzigingen; die gaan mee naar de Pi."
    fi
    echo
    echo "Deploy van: $(git branch --show-current) @ $(git rev-parse --short HEAD)  ->  $DOEL"
    "${SSH[@]}" 'echo "Verbonden met $(hostname)"'
}

sync_files() {
    # README stap 3, via rsync. $1 = "" of "-n" (dry-run).
    local dry="$1"
    local ssh_cmd="ssh -i '$KEY' -p $PI_PORT -o ConnectTimeout=10"
    echo "-- sync package + scripts -> ~/AudioController"
    # shellcheck disable=SC2086
    rsync -rvzt $dry \
        --exclude="fontawesome*" --exclude="bootstrap*" \
        --exclude="*.pyc" --exclude="__pycache__" --exclude=".pytest_cache" \
        --exclude=".DS_Store" \
        -e "$ssh_cmd" \
        ./audio_controller ./run_audio_controller.sh ./audio_controller.service \
        "$PI_USER@$PI_HOST:~/AudioController/"
    echo "-- sync kiosk-launcher -> ~/Desktop"
    # shellcheck disable=SC2086
    rsync -vzt $dry -e "$ssh_cmd" \
        ./audio_controller.html "$PI_USER@$PI_HOST:~/Desktop/"
}

do_backup() {
    # Download de HUIDIGE Pi-bestanden naar $BACKUP_DIR/<locatie>/<timestamp>/ zodat
    # je kunt terugrollen. Zelfde exclude-set als de deploy plus de venv: alleen wat
    # een deploy kan overschrijven wordt bewaard. Mislukt de backup, dan stopt alles
    # (tenzij --no-backup): eerst veiligstellen, dan pas pushen.
    local ts dest
    ts=$(date +%Y%m%d_%H%M%S)
    dest="$BACKUP_DIR/$LOC/$ts"
    mkdir -p "$dest"
    echo "-- backup: download huidige bestanden van $DOEL"
    echo "           -> $dest"
    # shellcheck disable=SC2086
    if rsync -rzt \
        --exclude="pyenv" --exclude="fontawesome*" --exclude="bootstrap*" \
        --exclude="*.pyc" --exclude="__pycache__" --exclude=".pytest_cache" \
        -e "ssh -i '$KEY' -p $PI_PORT -o ConnectTimeout=10" \
        "$PI_USER@$PI_HOST:~/AudioController/" "$dest/"; then
        local aantal
        aantal=$(ls -1d "$BACKUP_DIR/$LOC"/*/ 2>/dev/null | wc -l | tr -d ' ')
        echo "   backup klaar ($(du -sh "$dest" 2>/dev/null | cut -f1)); $aantal backup(s) bewaard voor $LOC"
        # standaard alle backups bewaren; alleen prunen als KEEP_BACKUPS > 0
        if [ "$KEEP_BACKUPS" -gt 0 ]; then
            # macOS-veilige prune (geen xargs -r): verwijder alles voorbij de N nieuwste
            ls -1dt "$BACKUP_DIR/$LOC"/*/ 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | while read -r old; do
                rm -rf "$old"
            done
        fi
    else
        echo "   FOUT: backup mislukt; er wordt NIETS gepusht."
        echo "   (Eerste keer? Accepteer de host-key handmatig, of gebruik --no-backup om te forceren.)"
        rmdir "$dest" 2>/dev/null || true
        exit 1
    fi
}

case "$ACTIE" in

    backup)
        do_backup
        ;;

    health)
        echo "Healthcheck $LOC:"
        healthcheck
        ;;

    status)
        echo "Status van $DOEL:"
        "${SSH[@]}" "
            echo \"host:     \$(hostname)\"
            grep -h __version__ $REMOTE_APP/__init__.py 2>/dev/null | head -1 | sed 's/^/versie:   /' || true
            echo \"service:  \$(systemctl is-active $SERVICE 2>/dev/null || true), sinds \$(systemctl show -p ActiveEnterTimestamp --value $SERVICE 2>/dev/null || echo '?')\"
            echo \"uptime:  \$(uptime)\"
            echo \"schijf:   \$(df -h / | tail -1 | awk '{print \$3\" gebruikt van \"\$2\" (\"\$5\")\"}')\"
            echo \"geheugen: \$(free -m 2>/dev/null | awk '/^Mem:/{print \$3\" MB gebruikt van \"\$2\" MB\"}' || true)\"
            echo \"temp:     \$(vcgencmd measure_temp 2>/dev/null || echo 'n.v.t.')\"
        "
        echo
        healthcheck
        ;;

    logs)
        echo "Laatste 40 logregels van $SERVICE op $LOC:"
        "${SSH[@]}" "sudo journalctl -u $SERVICE -n 40 --no-pager 2>/dev/null || sudo systemctl status $SERVICE --no-pager -l | tail -40"
        ;;

    restart)
        bevestig "Service herstarten op $DOEL?"
        "${SSH[@]}" "sudo systemctl restart $SERVICE && sleep 2 && systemctl is-active $SERVICE"
        healthcheck
        ;;

    update)
        preflight
        if [ -z "$DRY_RUN" ]; then
            bevestig "Updaten van $DOEL?"
            [ "$DO_BACKUP" -eq 1 ] && do_backup || echo "-- backup overgeslagen (--no-backup)"
        fi
        sync_files "$DRY_RUN"
        if [ -n "$DRY_RUN" ]; then
            echo "Dry-run klaar - er is niets gewijzigd op de Pi."
            exit 0
        fi
        echo "Let op: audio_controller.service is meegekopieerd maar niet geactiveerd."
        echo "        Gebruik 'volledige deploy' (--full) als de systemd-unit is gewijzigd."
        if [ "$RESTART" -eq 1 ]; then
            "${SSH[@]}" "sudo systemctl restart $SERVICE && sleep 2 && systemctl is-active $SERVICE"
        else
            echo "Service niet herstart (--no-restart); wijzigingen zijn pas actief na een herstart."
        fi
        healthcheck
        ;;

    full)
        preflight
        echo
        echo "Volledige deploy herinstalleert de systemd-unit uit audio_controller.service."
        [ "$LOC" = "wierden" ] && echo "  NB: die unit gebruikt /home/pi-paden; controleer of dat op wierden klopt."
        bevestig "Volledige deploy naar $DOEL?"
        [ "$DO_BACKUP" -eq 1 ] && do_backup || echo "-- backup overgeslagen (--no-backup)"
        sync_files ""
        echo "-- systemd-unit (her)installeren + herstarten (stap 4)"
        "${SSH[@]}" "
            set -e
            sudo cp ~/AudioController/$SERVICE /etc/systemd/system/$SERVICE
            sudo chmod 777 ~/AudioController/run_audio_controller.sh
            sudo systemctl daemon-reload
            sudo systemctl enable $SERVICE
            sudo systemctl restart $SERVICE
            sleep 2
            systemctl is-active $SERVICE
        "
        healthcheck
        ;;
esac
