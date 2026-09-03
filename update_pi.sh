#!/bin/bash
# update_pi.sh - AudioController op een van de Pi's bijwerken/beheren vanaf deze checkout.
# Update volgt README stap 2.3 (dependencies in de venv, nu via setup.py install_requires),
# stap 3 (rsync i.p.v. scp) en stap 4 (service herstarten/herinstalleren).
# LET OP: bevat deploy-details (hostnames/IP/poort/users) van de gergem-locaties;
# bewust in de repo zodat elke checkout dezelfde locaties kent.
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
#   ./update_pi.sh west --deps         alleen venv-dependencies (her)installeren via setup.py (geen sync)
#   ./update_pi.sh west --no-deps      sla de dependency-installatie bij update/full over
#   ./update_pi.sh west --health       snelle HTTP-healthcheck (wijzigt niets)
#   ./update_pi.sh west --status       software/systeem-status van de Pi (wijzigt niets)
#   ./update_pi.sh west --logs         laatste service-logregels (wijzigt niets)
#   ./update_pi.sh west --restart      alleen de service herstarten (geen sync)
#   ./update_pi.sh west --rollback     laatste backup terugzetten (bestanden) + service herstarten
#   ./update_pi.sh west --rollback=20260903_211150   een specifieke backup (map of datum-tijd) terugzetten
#   ./update_pi.sh west --rollback --with-config     ook de config (.audio_controller_*) uit de backup terugzetten
#   ./update_pi.sh west --no-tests     preflight zonder pytest
#   ./update_pi.sh west --skip-frontend-check   deployen ook al is main.js ouder dan de transcrypt-bronnen
#
# KEY=/pad/naar/key    overschrijft de ssh-key (standaard ~/.ssh/rpi_ed25519).
# BACKUP_DIR=/pad      overschrijft de backup-map (standaard ~/AudioController_pi_backups).
# KEEP_BACKUPS=N       houd alleen de N nieuwste backups per locatie (standaard 0 = alles bewaren).
# TEST_HOST=u@h:p      richt alle acties op een ander adres (alleen om het script te testen).
#
# Preflight (update/full): pytest moet slagen (--no-tests om over te slaan), main.js moet
# nieuwer zijn dan de transcrypt-bronnen (--skip-frontend-check), en de Pi moet bereikbaar
# zijn. Elke ssh/rsync heeft keepalive (dode verbinding = na ~30 s een fout i.p.v. eeuwig
# hangen) en de pip-stappen op de Pi hebben een tijdslimiet. Mislukt de herstart, dan
# toont het script de laatste logregels en wijst het op --rollback.
#
# Rollback: zet de bestanden uit een backup-map terug (standaard de nieuwste) en herstart.
# De huidige staat wordt eerst zelf gebackupt (tenzij --no-backup), dus ook een rollback is
# omkeerbaar. Alleen met --with-config gaat ook de config uit backup/home/ terug (de service
# wordt daarvoor gestopt, zodat de draaiende app hem niet overschrijft). Bestanden die de
# nieuwere versie had toegevoegd blijven staan (rsync zonder --delete); voor Python is dat
# onschadelijk. Elke deploy zet ook deploy_info.txt (branch/commit/datum) op de Pi; --status
# toont dat, zodat je ziet wat er precies draait.
#
# Backup: update en volledige deploy downloaden ALTIJD eerst de huidige Pi-bestanden
# naar $BACKUP_DIR/<locatie>/<datum-tijd>/ voordat er iets wordt overschreven (te
# omzeilen met --no-backup). Elke backup krijgt een eigen datum-tijd-submap, dus ze
# stapelen en je houdt er meerdere. --backup doet alleen dat downloaden, zonder te pushen.
# Dependencies: update en volledige deploy draaien na de sync `pip install --editable
# ./audio_controller` in de venv (~/AudioController/pyenv) op de Pi, zodat de runtime-
# dependencies uit setup.py (install_requires: tornado, python-socketio, pyserial,
# python-decouple, onvif-zeep, requests) altijd aanwezig zijn. Ontbreekt de venv, dan
# wordt hij aangemaakt. Vereist internet op de Pi; met --no-deps sla je dit over.
# De optionele GPIO-packages (gpiozero, rpi.gpio; README stap 2.3) blijven handwerk.
#
# Naast ~/AudioController/ gaat ook de config mee, in de submap home/:
# .audio_controller_settings.json (settings/sources/destinations/psalmbord/cameras/users),
# .audio_controller_settings.pickle (legacy, pre-1.5.0), .audio_controller_users.txt en
# .audio_controller_cookie.txt. LET OP: de app zoekt die in Path.home() van de user
# waaronder hij draait. De service draait als root (User=root in de unit), dus de
# LIVE config staat in /root/, niet in /home/pi/. Het script leest de service-user uit
# de unit en haalt de config uit diens home (via sudo). Een deploy raakt die niet aan,
# maar zo kun je ook de instellingen van dat moment terugzetten. Een eventuele kopie
# in /home/pi/ (van een handmatige start als pi) is NIET wat de service gebruikt.
#
# Wat wordt gesynct (README stap 3):
#   ./audio_controller          -> ~/AudioController   (de package; de nieuwste lokale main*.js
#                                                       gaat apart mee als static/js/main.js)
#   ./run_audio_controller.sh   -> ~/AudioController
#   ./audio_controller.service  -> ~/AudioController    (alleen geactiveerd bij --full)
#   ./audio_controller.html     -> ~/Desktop            (kiosk-launcher)
# Niet meegesynct: vendored assets (bootstrap*/fontawesome*) - die staan al op de Pi en
# wijzigen niet; en *.pyc/__pycache__/.pytest_cache/*.egg-info/.DS_Store.
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
ACTIE=""        # update | full | backup | deps | health | status | logs | restart | rollback
DRY_RUN=""
RESTART=1
ASSUME_YES=0
DO_BACKUP=1     # update/full downloaden altijd eerst de huidige Pi-bestanden
DO_DEPS=1       # update/full installeren na de sync de dependencies uit setup.py
DO_TESTS=1      # preflight draait pytest
CHECK_FRONTEND=1
ROLLBACK_FROM=""    # leeg = nieuwste backup van de locatie
ROLLBACK_CONFIG=0
for arg in "$@"; do
    case "$arg" in
        --rollback)   ACTIE="rollback" ;;
        --rollback=*) ACTIE="rollback"; ROLLBACK_FROM="${arg#--rollback=}" ;;
        --with-config) ROLLBACK_CONFIG=1 ;;
        --no-tests)   DO_TESTS=0 ;;
        --skip-frontend-check) CHECK_FRONTEND=0 ;;
        --dry-run)    ACTIE="update"; DRY_RUN="-n" ;;
        --no-restart) ACTIE="update"; RESTART=0 ;;
        --no-backup)  DO_BACKUP=0 ;;
        --yes)        [ -z "$ACTIE" ] && ACTIE="update"; ASSUME_YES=1 ;;
        --full)       ACTIE="full" ;;
        --backup)     ACTIE="backup" ;;
        --deps)       ACTIE="deps" ;;
        --no-deps)    DO_DEPS=0 ;;
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
if [ -n "${TEST_HOST:-}" ]; then
    # alleen voor het testen van het script: user@host:poort
    PI_USER="${TEST_HOST%%@*}"; rest="${TEST_HOST#*@}"; PI_HOST="${rest%%:*}"; PI_PORT="${rest##*:}"
    echo "LET OP: TEST_HOST actief, doel is $PI_USER@$PI_HOST:$PI_PORT i.p.v. $LOC"
fi
DOEL="$PI_USER@$PI_HOST (poort $PI_PORT)"
# keepalive: een Pi die tijdens de deploy wegvalt geeft na ~30 s een fout i.p.v. een hangend script
SSH_OPTS=(-i "$KEY" -p "$PI_PORT" -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3)
SSH=(ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST")
SSH_E="ssh -i '$KEY' -p $PI_PORT -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3"   # voor rsync -e

# --- actie kiezen ---
if [ -z "$ACTIE" ]; then
    if [ -t 0 ]; then
        echo
        echo "${BOLD}Actie voor $LOC${RESET} ${DIM}$DOEL${RESET}"
        echo "  1) update             ${DIM}backup + sync alle bestanden + deps + service-herstart${RESET}"
        echo "  2) dry-run            ${DIM}toon wat update zou wijzigen, verandert niets${RESET}"
        echo "  3) update zonder herstart"
        echo "  4) volledige deploy   ${DIM}backup + alles + deps + systemd-unit (her)installeren (stap 4)${RESET}"
        echo "  5) backup             ${DIM}download huidige Pi-bestanden lokaal, zonder te pushen${RESET}"
        echo "  6) dependencies       ${DIM}venv-deps uit setup.py (her)installeren, geen sync (stap 2.3)${RESET}"
        echo "  7) healthcheck        ${DIM}snelle HTTP-check, wijzigt niets${RESET}"
        echo "  8) status             ${DIM}versie, service, uptime, schijf, temperatuur${RESET}"
        echo "  9) logs               ${DIM}laatste 40 regels van de service${RESET}"
        echo " 10) herstart service   ${DIM}geen sync, alleen systemctl restart${RESET}"
        echo " 11) rollback           ${DIM}laatste backup terugzetten + herstart (config alleen met --with-config)${RESET}"
        echo "  q) stoppen"
        while true; do
            read -r -p "Keuze [1-11, q]: " k
            case "$k" in
                1) ACTIE="update"; break ;;
                2) ACTIE="update"; DRY_RUN="-n"; break ;;
                3) ACTIE="update"; RESTART=0; break ;;
                4) ACTIE="full"; break ;;
                5) ACTIE="backup"; break ;;
                6) ACTIE="deps"; break ;;
                7) ACTIE="health"; break ;;
                8) ACTIE="status"; break ;;
                9) ACTIE="logs"; break ;;
                10) ACTIE="restart"; break ;;
                11) ACTIE="rollback"; break ;;
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

service_home() {
    # Home-map van de user waaronder de service draait (User= in de unit; leeg = root).
    # Daar staan de .audio_controller_* bestanden die de LIVE service gebruikt.
    "${SSH[@]}" '
        u=$(systemctl show -p User --value '"$SERVICE"' 2>/dev/null)
        [ -n "$u" ] || u=root
        h=$(getent passwd "$u" | cut -d: -f6)
        echo "$u:${h:-/root}"
    '
}

check_instance() {
    # Na een (her)start: precies één audio_controller-proces, en tonen als wie en met
    # welke config die draait. Meer dan één (bijv. een handmatige start als pi naast de
    # service) betekent poortconflicten en/of een tweede, afwijkende settings-file.
    echo "-- controle: draaiende instantie(s)"
    "${SSH[@]}" '
        pids=$(pgrep -f "^python3 -m audio_controller$" | tr "\n" " ")
        n=$(echo $pids | wc -w)
        for p in $pids; do
            u=$(ps -o user= -p "$p" | tr -d " ")
            h=$(sudo -n cat /proc/$p/environ 2>/dev/null | tr "\0" "\n" | sed -n "s/^HOME=//p")
            [ -n "$h" ] || h=$(getent passwd "$u" | cut -d: -f6)
            f="$h/.audio_controller_settings.json"
            info=$(sudo -n stat -c "%s bytes, %y" "$f" 2>/dev/null | cut -d. -f1 || echo "ontbreekt")
            echo "   pid $p  user=$u  config=$f  ($info)"
        done
        if [ "$n" -eq 1 ]; then
            echo "   ok: precies 1 instantie (de systemd-service)"
        elif [ "$n" -eq 0 ]; then
            echo "   FOUT: geen audio_controller-proces gevonden"
        else
            echo "   WAARSCHUWING: $n instanties! Alleen de systemd-service hoort te draaien;"
            echo "   stop de andere (kill <pid>) en herstart daarna de service (--restart)."
        fi
    '
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
    # De app hernoemt main.js bij het starten naar main-<tijdstempel>.js (cache-busting);
    # ook de lokale pytest-run doet dat. De 'gecompileerde frontend' is dus de nieuwste
    # niet-lege main*.js.
    local mainjs
    mainjs=$(ls -t audio_controller/audio_controller/static/js/main*.js 2>/dev/null | while read -r f; do [ -s "$f" ] && echo "$f" && break; done)
    if [ -z "$mainjs" ]; then
        echo "FOUT: geen gecompileerde frontend (static/js/main*.js ontbreekt of is leeg)."
        echo "Compileer eerst: python -m manage_env compile_on_save (zie README)."
        exit 1
    fi
    MAINJS="$mainjs"
    if [ "$CHECK_FRONTEND" -eq 1 ]; then
        # main.js moet nieuwer zijn dan alle transcrypt-bronnen, anders gaat een oude UI mee
        local stale
        stale=$(find transcrypt/python -name '*.py' -not -path '*/__target__/*' -newer "$mainjs" 2>/dev/null | head -5)
        if [ -n "$stale" ]; then
            echo "FOUT: main.js is ouder dan deze transcrypt-bronnen:"
            echo "$stale" | sed 's/^/   /'
            echo "Compileer eerst (transcrypt + webpack, zie README), of gebruik --skip-frontend-check."
            exit 1
        fi
    fi
    if [ "$DO_TESTS" -eq 1 ]; then
        if [ -x pyenv/bin/python ]; then
            echo "-- preflight: pytest"
            local out
            if ! out=$(cd audio_controller && ../pyenv/bin/python -m pytest -q -x 2>&1); then
                echo "$out" | tail -15
                echo "FOUT: tests falen; er wordt niets gedeployed (--no-tests om te forceren)."
                exit 1
            fi
            echo "   $(echo "$out" | tail -1)"
        else
            echo "LET OP: geen lokale venv (pyenv/); tests overgeslagen. Maak hem met: bash create_venv.sh"
        fi
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "LET OP: working tree bevat niet-gecommitte wijzigingen; die gaan mee naar de Pi."
    fi
    echo
    echo "Deploy van: $(git branch --show-current) @ $(git rev-parse --short HEAD)  ->  $DOEL"
    "${SSH[@]}" 'echo "Verbonden met $(hostname)"'
}

push_frontend() {
    # $1 = lokale main*.js, $2 = "" of "-n". Gaat als 'main.js' naar de Pi: de app hernoemt
    # die bij het starten naar main-<tijdstempel>.js en ruimt oudere main-*.js zelf op
    # (handlers.get_js_filename). Zo blijft er nooit een oudere/nieuwere versie naast staan,
    # ook niet na een rollback (de app kiest anders de hoogste tijdstempel, en dat zou de
    # teruggedraaide versie zijn).
    local src="$1" dry="$2"
    echo "-- frontend: $(basename "$src") -> static/js/main.js"
    # shellcheck disable=SC2086
    rsync -vzt $dry -e "$SSH_E" "$src" \
        "$PI_USER@$PI_HOST:~/AudioController/audio_controller/audio_controller/static/js/main.js"
}

sync_files() {
    # README stap 3, via rsync. $1 = "" of "-n" (dry-run).
    local dry="$1"
    local ssh_cmd="$SSH_E"
    # deploy_info.txt: wat er precies op de Pi staat (--status toont het)
    local info
    info=$(mktemp -d)/deploy_info.txt
    printf 'branch: %s\ncommit: %s\ndatum:  %s\nvan:    %s@%s\n' \
        "$(git branch --show-current)" "$(git rev-parse --short HEAD)" "$(date '+%Y-%m-%d %H:%M:%S')" "$USER" "$(hostname)" > "$info"
    echo "-- sync package + scripts -> ~/AudioController"
    # shellcheck disable=SC2086
    rsync -rvzt $dry \
        --exclude="fontawesome*" --exclude="bootstrap*" --exclude="main*.js" \
        --exclude="*.pyc" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.egg-info" \
        --exclude=".DS_Store" \
        -e "$ssh_cmd" \
        ./audio_controller ./run_audio_controller.sh ./audio_controller.service "$info" \
        "$PI_USER@$PI_HOST:~/AudioController/"
    rm -rf "$(dirname "$info")"
    push_frontend "$MAINJS" "$dry"
    echo "-- sync kiosk-launcher -> ~/Desktop"
    # shellcheck disable=SC2086
    rsync -vzt $dry -e "$ssh_cmd" \
        ./audio_controller.html "$PI_USER@$PI_HOST:~/Desktop/"
}

do_backup() {
    # Download de HUIDIGE Pi-bestanden naar $BACKUP_DIR/<locatie>/<timestamp>/ zodat
    # je kunt terugrollen. Zelfde exclude-set als de deploy plus de venv: alleen wat
    # een deploy kan overschrijven wordt bewaard. Daarnaast de config-bestanden
    # (.audio_controller_*) uit de home-map van de SERVICE-user (root -> /root/) naar
    # <timestamp>/home/, zodat ook de live instellingen van dat moment bewaard blijven.
    # Mislukt de backup, dan stopt alles (tenzij --no-backup): eerst veiligstellen,
    # dan pas pushen.
    local ts dest ssh_cmd svc_user svc_home
    ts=$(date +%Y%m%d_%H%M%S)
    dest="$BACKUP_DIR/$LOC/$ts"
    ssh_cmd="$SSH_E"
    IFS=: read -r svc_user svc_home <<< "$(service_home)"
    if [ -z "$svc_home" ]; then
        echo "   FOUT: kan de service-user/home niet bepalen (Pi onbereikbaar?); er wordt NIETS gepusht."
        exit 1
    fi
    mkdir -p "$dest/home"
    echo "-- backup: download huidige bestanden van $DOEL"
    echo "           -> $dest"
    echo "           config van service-user $svc_user uit $svc_home/ -> home/"
    printf 'Config in deze map komt van %s (home van service-user %s) op %s.\nTerugzetten: sudo cp .audio_controller_* %s/ en daarna de service herstarten.\n' \
        "$svc_home" "$svc_user" "$LOC" "$svc_home" > "$dest/home/HERKOMST.txt"
    # Tweede rsync: config via include/exclude-filter i.p.v. losse bestandsnamen, zodat
    # een ontbrekend bestand (bijv. de legacy pickle) geen fout geeft; --rsync-path met
    # sudo omdat /root/ niet leesbaar is voor de ssh-user.
    # shellcheck disable=SC2086
    if rsync -rzt \
        --exclude="pyenv" --exclude="fontawesome*" --exclude="bootstrap*" \
        --exclude="*.pyc" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="*.egg-info" \
        -e "$ssh_cmd" \
        "$PI_USER@$PI_HOST:~/AudioController/" "$dest/" \
    && rsync -dzt --rsync-path="sudo -n rsync" \
        --include=".audio_controller_*" --exclude="*" \
        -e "$ssh_cmd" \
        "$PI_USER@$PI_HOST:$svc_home/" "$dest/home/"; then
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
        rm -rf "$dest"   # eigen, zojuist aangemaakte map; een halve backup mag nooit als 'nieuwste' gelden
        exit 1
    fi
}

install_deps() {
    # README stap 2.3, maar via setup.py: `pip install --editable ./audio_controller`
    # in de venv op de Pi installeert de install_requires (tornado, python-socketio,
    # pyserial, python-decouple, onvif-zeep, requests). Editable, net als in
    # create_venv.sh: run_audio_controller.sh draait uit de broncode-map, dus er komt
    # geen kopie in site-packages die na een rsync achter zou lopen. Ontbreekt de venv
    # (bijv. nieuwe Pi, of onvif ModuleNotFoundError omdat het systeem-python werd
    # gebruikt), dan wordt hij aangemaakt. Draait als de Pi-user; de service (root)
    # kan de venv gewoon lezen.
    echo "-- dependencies: venv + pip install --editable ./audio_controller (stap 2.3)"
    "${SSH[@]}" '
        set -e
        cd ~/AudioController
        if [ ! -x pyenv/bin/python ]; then
            echo "   venv ontbreekt: python3 -m venv pyenv"
            python3 -m venv pyenv
        fi
        echo "   venv: $(pyenv/bin/python --version 2>&1) in $(pwd)/pyenv"
        # tijdslimiet: een hangende PyPI-verbinding mag de deploy niet blokkeren
        timeout 300 pyenv/bin/python -m pip install --quiet --upgrade pip \
            || { echo "   FOUT: pip-upgrade mislukt of duurde >5 min (internet op de Pi?); --no-deps om over te slaan"; exit 1; }
        timeout 600 pyenv/bin/python -m pip install --quiet --editable ./audio_controller \
            || { echo "   FOUT: pip install mislukt of duurde >10 min (internet op de Pi?); --no-deps om over te slaan"; exit 1; }
        echo "   geinstalleerd:"
        pyenv/bin/python -m pip list --format=columns 2>/dev/null \
            | grep -i -E "^(audio[-_]controller|tornado|python-socketio|pyserial|python-decouple|onvif-zeep|requests|gpiozero|RPi\.GPIO) " \
            | sed "s/^/     /"
        pyenv/bin/python -m pip check >/dev/null 2>&1 && echo "   pip check: ok" || echo "   pip check: WAARSCHUWING, conflicterende versies (zie: pyenv/bin/python -m pip check)"
        pyenv/bin/python -c "import tornado, socketio, serial, decouple, onvif, requests" \
            && echo "   import-test: ok"
    '
}

restart_service() {
    echo "-- service herstarten"
    if "${SSH[@]}" "sudo systemctl restart $SERVICE && sleep 2 && systemctl is-active $SERVICE"; then
        check_instance
    else
        echo
        echo "FOUT: $SERVICE is niet actief na de herstart. Laatste logregels:"
        "${SSH[@]}" "sudo journalctl -u $SERVICE -n 30 --no-pager 2>/dev/null || sudo systemctl status $SERVICE --no-pager -l | tail -30" || true
        echo
        echo "Terugrollen naar de laatste backup: ./update_pi.sh $LOC --rollback"
        exit 1
    fi
}

do_rollback() {
    # Bestanden uit een backup-map terugzetten. Standaard de nieuwste backup van deze
    # locatie; anders --rollback=<map> of --rollback=<datum-tijd>. Kiest de bron VOOR de
    # eigen pre-rollback backup, anders zou "nieuwste" naar de kapotte staat wijzen.
    local src="$ROLLBACK_FROM"
    if [ -z "$src" ]; then
        # nieuwste map die echt een package bevat (geen lege/halve backup)
        src=$(for d in "$BACKUP_DIR/$LOC"/*/; do [ -d "$d/audio_controller" ] && echo "$d"; done 2>/dev/null | sort | tail -1)
    elif [ ! -d "$src" ] && [ -d "$BACKUP_DIR/$LOC/$src" ]; then
        src="$BACKUP_DIR/$LOC/$src"
    fi
    src="${src%/}"
    if [ -z "$src" ] || [ ! -d "$src/audio_controller" ]; then
        echo "FOUT: geen bruikbare backup gevonden (verwacht $BACKUP_DIR/$LOC/<datum-tijd>/audio_controller/)."
        ls -1d "$BACKUP_DIR/$LOC"/*/ 2>/dev/null | sed 's/^/   /' || true
        exit 1
    fi
    "${SSH[@]}" 'echo "Verbonden met $(hostname)"' || { echo "FOUT: $DOEL is niet bereikbaar; rollback afgebroken."; exit 1; }
    echo "Rollback voor $LOC vanuit: $src"
    [ -f "$src/deploy_info.txt" ] && sed 's/^/   /' "$src/deploy_info.txt"
    grep -h __version__ "$src/audio_controller/audio_controller/__init__.py" 2>/dev/null | sed 's/^/   /' || true
    echo "   bestanden: $(ls -1 "$src" | tr '\n' ' ')"
    if [ "$ROLLBACK_CONFIG" -eq 1 ]; then
        [ -d "$src/home" ] || { echo "FOUT: --with-config, maar $src/home/ ontbreekt."; exit 1; }
        echo "   config:    $(ls -1A "$src/home" | tr '\n' ' ')"
    else
        echo "   config:    blijft zoals hij nu is (--with-config om ook home/ terug te zetten)"
    fi
    bevestig "Deze backup terugzetten op $DOEL en de service herstarten?"
    if [ "$DO_BACKUP" -eq 1 ]; then
        do_backup
    else
        echo "-- pre-rollback backup overgeslagen (--no-backup)"
    fi
    local svc_user svc_home
    if [ "$ROLLBACK_CONFIG" -eq 1 ]; then
        IFS=: read -r svc_user svc_home <<< "$(service_home)"
        [ -n "$svc_home" ] || { echo "FOUT: kan de service-home niet bepalen; rollback afgebroken (service niet gestopt)."; exit 1; }
        echo "-- service stoppen (config wordt vervangen)"
        "${SSH[@]}" "sudo systemctl stop $SERVICE"
    fi
    echo "-- bestanden terugzetten -> ~/AudioController"
    local items=("$src/audio_controller")
    [ -f "$src/run_audio_controller.sh" ] && items+=("$src/run_audio_controller.sh")
    [ -f "$src/audio_controller.service" ] && items+=("$src/audio_controller.service")
    [ -f "$src/deploy_info.txt" ] && items+=("$src/deploy_info.txt")
    rsync -rvzt --exclude="*.pyc" --exclude="__pycache__" --exclude=".DS_Store" --exclude="main*.js" \
        -e "$SSH_E" "${items[@]}" "$PI_USER@$PI_HOST:~/AudioController/"
    local bak_js
    bak_js=$(ls -t "$src"/audio_controller/audio_controller/static/js/main*.js 2>/dev/null | while read -r f; do [ -s "$f" ] && echo "$f" && break; done)
    if [ -n "$bak_js" ]; then
        push_frontend "$bak_js" ""
    else
        echo "LET OP: geen main*.js in de backup; de frontend op de Pi blijft de huidige."
    fi
    if [ -f "$src/audio_controller.html" ]; then
        rsync -vzt -e "$SSH_E" "$src/audio_controller.html" "$PI_USER@$PI_HOST:~/Desktop/"
    fi
    if [ "$ROLLBACK_CONFIG" -eq 1 ]; then
        echo "-- config terugzetten -> $svc_home/ (service-user $svc_user)"
        rsync -dzt --rsync-path="sudo -n rsync" --include=".audio_controller_*" --exclude="*" \
            -e "$SSH_E" "$src/home/" "$PI_USER@$PI_HOST:$svc_home/"
    fi
    [ "$DO_DEPS" -eq 1 ] && install_deps || echo "-- dependencies overgeslagen (--no-deps)"
    restart_service
    healthcheck
    echo "Rollback klaar. De staat van vóór de rollback staat in de nieuwste backup-map."
}

case "$ACTIE" in

    backup)
        do_backup
        ;;

    rollback)
        do_rollback
        ;;

    deps)
        bevestig "Dependencies (her)installeren in de venv op $DOEL?"
        install_deps
        echo "Let op: de service is niet herstart; gebruik --restart als nieuwe packages actief moeten worden."
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
            [ -f ~/AudioController/deploy_info.txt ] && sed 's/^/deploy:   /' ~/AudioController/deploy_info.txt || echo 'deploy:   (geen deploy_info.txt; van voor dit script)'
            echo \"service:  \$(systemctl is-active $SERVICE 2>/dev/null || true), sinds \$(systemctl show -p ActiveEnterTimestamp --value $SERVICE 2>/dev/null || echo '?')\"
            echo \"uptime:  \$(uptime)\"
            echo \"schijf:   \$(df -h / | tail -1 | awk '{print \$3\" gebruikt van \"\$2\" (\"\$5\")\"}')\"
            echo \"geheugen: \$(free -m 2>/dev/null | awk '/^Mem:/{print \$3\" MB gebruikt van \"\$2\" MB\"}' || true)\"
            echo \"temp:     \$(vcgencmd measure_temp 2>/dev/null || echo 'n.v.t.')\"
        "
        echo
        check_instance
        echo
        healthcheck
        ;;

    logs)
        echo "Laatste 40 logregels van $SERVICE op $LOC:"
        "${SSH[@]}" "sudo journalctl -u $SERVICE -n 40 --no-pager 2>/dev/null || sudo systemctl status $SERVICE --no-pager -l | tail -40"
        ;;

    restart)
        bevestig "Service herstarten op $DOEL?"
        restart_service
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
        [ "$DO_DEPS" -eq 1 ] && install_deps || echo "-- dependencies overgeslagen (--no-deps)"
        echo "Let op: audio_controller.service is meegekopieerd maar niet geactiveerd."
        echo "        Gebruik 'volledige deploy' (--full) als de systemd-unit is gewijzigd."
        if [ "$RESTART" -eq 1 ]; then
            restart_service
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
        [ "$DO_DEPS" -eq 1 ] && install_deps || echo "-- dependencies overgeslagen (--no-deps)"
        echo "-- systemd-unit (her)installeren (stap 4)"
        "${SSH[@]}" "
            set -e
            sudo cp ~/AudioController/$SERVICE /etc/systemd/system/$SERVICE
            sudo chmod 777 ~/AudioController/run_audio_controller.sh
            sudo systemctl daemon-reload
            sudo systemctl enable $SERVICE
        "
        restart_service
        healthcheck
        ;;
esac
