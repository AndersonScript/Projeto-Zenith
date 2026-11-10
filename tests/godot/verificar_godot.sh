#!/usr/bin/env bash
# Verifica o Corpo (Godot) com o Godot DE VERDADE, no Linux. Nada disto roda no Windows; serve para eu (ou você, no WSL)
# conferir sintaxe e tirar prints do layout de celular sem abrir um celular.
#
#   GODOT=/caminho/Godot_v4.7.1-stable_linux.x86_64  tests/godot/verificar_godot.sh sintaxe
#   GODOT=...  tests/godot/verificar_godot.sh prints  [pasta_de_saida]
#
# "sintaxe": roda --check-only em cada .gd de body/zenith (falha = código de saída 1).
# "prints":  precisa de xvfb (apt install xvfb libgl1-mesa-dri). Copia o projeto para uma pasta temporária, liga um
#            autoload de teste (shot_auto.gd) e salva PNGs da interface em 390x844: chat normal, gaveta, botões "Parar",
#            lista de Configurações, 4 seções, a linha do modelo de fala, Memórias, aprovação de ação o teclado virtual simulado e o avatar simples (a janela principal sai em celular_avatar_simples_corpo.png). NÃO altera o projeto original.
set -u
GODOT="${GODOT:?defina GODOT=/caminho/do/godot}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
PROJ="$RAIZ/body/zenith"
modo="${1:-sintaxe}"
if [ "$modo" = "sintaxe" ]; then
  ruins=0
  for f in "$PROJ"/*.gd; do
    n="$(basename "$f")"
    if ! timeout 60 "$GODOT" --headless --path "$PROJ" --check-only --script "res://$n" >/tmp/_gd.$$ 2>&1 \
       || grep -q -E "SCRIPT ERROR|Parse Error" /tmp/_gd.$$; then
      ruins=$((ruins+1)); echo "FALHA: $n"; grep -E "SCRIPT ERROR|Parse Error|at: " /tmp/_gd.$$ | head -4
    fi
  done
  rm -f /tmp/_gd.$$
  echo "arquivos com erro: $ruins"; [ "$ruins" = 0 ]; exit $?
fi
SAIDA="${2:-/tmp/zenith_prints}"; TMP="$(mktemp -d)"; mkdir -p "$SAIDA"
cp -r "$PROJ"/. "$TMP"/ && cp "$RAIZ/tests/godot/shot_auto.gd" "$TMP/_shot_auto.gd"
sed -i 's#^\[autoload\]#[autoload]\n\nShotAuto="*res://_shot_auto.gd"#' "$TMP/project.godot"
sed -i "s#/home/claude/shots#$SAIDA#g" "$TMP/_shot_auto.gd"
for cenario in "normal:" "gaveta:--visual-gaveta" "atividade:--visual-atividade" "config_lista:--visual-abrir=__lista__" "config_voz:--visual-abrir=Voz" "config_corpo:--visual-abrir=Corpo_/_VRM" "config_estudio:--visual-abrir=Estúdio" "config_chaves:--visual-abrir=Chaves_&_IAs" "memorias:--visual-memorias" "aprovacao:--visual-aprovacao" "config_modelo:--visual-abrir=Voz_--visual-modelo=63" "teclado:--celular-teclado=330" "avatar_simples:--aplicar-avatar=padrao_--corpo-estado=speaking_--corpo-expressao=happy"; do
  nome="${cenario%%:*}"; extra="${cenario#*:}"; extra="${extra//_/ }"
  timeout 150 xvfb-run -a -s "-screen 0 1600x1000x24" "$GODOT" --path "$TMP" --rendering-driver opengl3 --resolution 390x844 -- \
    --layout-celular --celular-tela=390x844 $extra --nome="celular_$nome" 2>&1 | grep -E "SCRIPT ERROR|JANELA"
done
rm -rf "$TMP"; echo "prints em: $SAIDA"
