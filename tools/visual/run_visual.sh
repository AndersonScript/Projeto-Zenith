#!/usr/bin/env bash
# Teste visual: sobe o Cérebro de mentira + Godot numa tela virtual (Xvfb) e tira prints.
# Uso: tools/visual/run_visual.sh <godot> <saida.png> [segundos] [-- args do jogo]
GODOT="$1"; OUT="$2"; ESPERA="${3:-22}"; shift 3 2>/dev/null
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$RAIZ/tools/visual/fake_brain.py" > /tmp/fake_brain.log 2>&1 &
FB=$!
sleep 1.5
export LIBGL_ALWAYS_SOFTWARE=1
xvfb-run -a -s "-screen 0 1600x900x24" bash -c "
  '$GODOT' --path '$RAIZ/body/zenith' --rendering-driver opengl3 --resolution 1280x720 -- --sem-aa $* > /tmp/godot_visual.log 2>&1 &
  GP=\$!
  sleep $ESPERA
  import -window root '$OUT' 2>/dev/null
  kill \$GP 2>/dev/null; sleep 1
"
kill $FB 2>/dev/null
