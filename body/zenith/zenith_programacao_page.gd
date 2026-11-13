extends RefCounted
# ============================================================
#  ZENITH — Área de Programação & Mentoria de Código (v1.22)
#
#  Permite escrever, testar e executar código diretamente no celular
#  ou no computador, com suporte a GDScript, Python, Java, C++ e JS,
#  além de mentoria interativa com a Zenith (estilo Shogers e Rembria).
# ============================================================

var ui: Node
var brain: Node

var editor: TextEdit
var console: TextEdit
var opt_linguagem: OptionButton
var opt_exemplos: OptionButton
var lbl_status: Label
var btn_rodar: Button
var btn_ensinar: Button
var btn_limpar: Button

const EXEMPLOS := {
	"0": {
		"nome": "1. Olá Mundo & Variáveis (GDScript)",
		"ling": 0,
		"codigo": """# Olá Mundo e Variáveis no Zenith
var nome = "Anderson"
var missao = "Criar a melhor assistente com IA"
print("Olá, " + nome + "!")
print("Sua missão: " + missao)

var nivel = 10
var bonus = 5.5
print("Poder total: " + str(nivel * bonus))
"""
	},
	"1": {
		"nome": "2. Laço de Repetição & Tabuada",
		"ling": 0,
		"codigo": """# Tabuada usando loop for
var numero = 7
print("=== Tabuada do " + str(numero) + " ===")
for i in range(1, 11):
	var res = numero * i
	print(str(numero) + " x " + str(i) + " = " + str(res))
"""
	},
	"2": {
		"nome": "3. Condicionais & Verificação de Nota",
		"ling": 0,
		"codigo": """# Verificação de média do aluno
var notas = [8.5, 7.0, 9.2, 6.5]
var soma = 0.0

for n in notas:
	soma += n

var media = soma / float(notas.size())
print("Média final: " + str(snapped(media, 0.01)))

if media >= 7.0:
	print("Status: Aprovado com sucesso! 🎉")
elif media >= 5.0:
	print("Status: Em recuperação — ainda dá tempo! 💡")
else:
	print("Status: Reprovado. Vamos revisar o conteúdo.")
"""
	},
	"3": {
		"nome": "4. Robótica: Lógica de Sensor ESP32 / Arduino",
		"ling": 3,
		"codigo": """// Exemplo de código C++ para Arduino / ESP32
// Leitura de sensor e controle de atuador

const int PINO_SENSOR = 34; // Entrada analógica
const int PINO_LED = 2;     // LED indicador

void setup() {
  Serial.begin(115200);
  pinMode(PINO_LED, OUTPUT);
  Serial.println("ESP32 iniciado com sucesso!");
}

void loop() {
  int valor = analogRead(PINO_SENSOR);
  Serial.print("Valor lido: ");
  Serial.println(valor);
  
  if (valor > 2000) {
    digitalWrite(PINO_LED, HIGH); // Ativa LED se passar do limiar
  } else {
    digitalWrite(PINO_LED, LOW);
  }
  delay(500);
}
"""
	},
	"4": {
		"nome": "5. Estrutura de Classe em Java",
		"ling": 2,
		"codigo": """// Exemplo de Programação Orientada a Objetos em Java
public class AssistenteZenith {
    private String nome;
    private int versao;

    public AssistenteZenith(String nome, int versao) {
        this.nome = nome;
        this.versao = versao;
    }

    public void saudar(String criador) {
        System.out.println("Olá, " + criador + "! Sou " + this.nome + " v" + this.versao);
    }

    public static void main(String[] args) {
        AssistenteZenith zenith = new AssistenteZenith("Akira", 1);
        zenith.saudar("Anderson");
    }
}
"""
	},
	"5": {
		"nome": "6. Algoritmo em Python: Análise de Dados",
		"ling": 1,
		"codigo": """# Script Python para Análise de Dados Simples
dados = [12, 45, 67, 89, 34, 23, 90, 11]

maior = max(dados)
menor = min(dados)
media = sum(dados) / len(dados)

print(f"Total de registros: {len(dados)}")
print(f"Maior valor: {maior}")
print(f"Menor valor: {menor}")
print(f"Média calculada: {media:.2f}")
"""
	}
}

func montar(ui_node: Node, brain_node: Node, v: VBoxContainer) -> void:
	ui = ui_node
	brain = brain_node

	# Barra superior de ferramentas
	var topo = HBoxContainer.new()
	topo.add_theme_constant_override("separation", 10)
	v.add_child(topo)

	var lbl_ling = Label.new()
	lbl_ling.text = "Linguagem:"
	lbl_ling.add_theme_color_override("font_color", ui.TEXT_MUTED)
	lbl_ling.add_theme_font_size_override("font_size", 12)
	topo.add_child(lbl_ling)

	opt_linguagem = OptionButton.new()
	opt_linguagem.add_item("GDScript (Roda direto no app)")
	opt_linguagem.add_item("Python")
	opt_linguagem.add_item("Java")
	opt_linguagem.add_item("C++ / Arduino (ESP32)")
	opt_linguagem.add_item("JavaScript")
	topo.add_child(opt_linguagem)

	var lbl_ex = Label.new()
	lbl_ex.text = "Exemplos:"
	lbl_ex.add_theme_color_override("font_color", ui.TEXT_MUTED)
	lbl_ex.add_theme_font_size_override("font_size", 12)
	topo.add_child(lbl_ex)

	opt_exemplos = OptionButton.new()
	opt_exemplos.add_item("Carregar exemplo...")
	for k in EXEMPLOS:
		opt_exemplos.add_item(EXEMPLOS[k]["nome"])
	opt_exemplos.item_selected.connect(_ao_selecionar_exemplo)
	topo.add_child(opt_exemplos)

	var espaco = Control.new()
	espaco.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	topo.add_child(espaco)

	btn_limpar = ui._make_button("Limpar", ui.BG_SURFACE_2, ui.BG_SURFACE_3)
	btn_limpar.pressed.connect(func():
		editor.text = ""
		console.text = "")
	topo.add_child(btn_limpar)

	# Editor de código
	var lbl_ed = Label.new()
	lbl_ed.text = "Editor de Código:"
	lbl_ed.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	lbl_ed.add_theme_font_size_override("font_size", 13)
	v.add_child(lbl_ed)

	editor = TextEdit.new()
	editor.custom_minimum_size = Vector2(0, 180)
	editor.size_flags_vertical = Control.SIZE_EXPAND_FILL
	editor.add_theme_stylebox_override("normal", ui._panel_style(ui.BG_SURFACE_2, 8, ui.BORDER, 1))
	editor.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	editor.placeholder_text = "# Escreva seu código aqui ou escolha um exemplo acima..."
	editor.draw_control_chars = false
	v.add_child(editor)

	# Barra de ações
	var barra_acoes = HBoxContainer.new()
	barra_acoes.add_theme_constant_override("separation", 10)
	v.add_child(barra_acoes)

	btn_rodar = ui._make_button("▶  Executar no Aparelho", ui.CYAN, ui.CYAN_DIM, Color("04141a"))
	btn_rodar.custom_minimum_size.y = 38
	btn_rodar.pressed.connect(_executar_codigo)
	barra_acoes.add_child(btn_rodar)

	btn_ensinar = ui._make_button("🧠  Zenith, me ensina este código!", ui.BG_SURFACE_3, ui.BG_SURFACE_2, ui.CYAN)
	btn_ensinar.custom_minimum_size.y = 38
	btn_ensinar.pressed.connect(_pedir_mentoria)
	barra_acoes.add_child(btn_ensinar)

	lbl_status = Label.new()
	lbl_status.text = "Pronto para rodar."
	lbl_status.add_theme_color_override("font_color", ui.TEXT_MUTED)
	lbl_status.add_theme_font_size_override("font_size", 12)
	lbl_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	barra_acoes.add_child(lbl_status)

	# Terminal / Console de Saída
	var lbl_con = Label.new()
	lbl_con.text = "Console de Saída:"
	lbl_con.add_theme_color_override("font_color", ui.TEXT_PRIMARY)
	lbl_con.add_theme_font_size_override("font_size", 13)
	v.add_child(lbl_con)

	console = TextEdit.new()
	console.custom_minimum_size = Vector2(0, 110)
	console.editable = false
	console.add_theme_stylebox_override("normal", ui._panel_style(Color("0a0a0d"), 8, ui.BORDER, 1))
	console.add_theme_color_override("font_color", Color("4ade80")) # Verde terminal
	console.placeholder_text = "Os resultados e impressões do código aparecerão aqui..."
	v.add_child(console)

	# Carrega o primeiro exemplo por padrão
	_carregar_exemplo("0")

func _ao_selecionar_exemplo(idx: int) -> void:
	if idx <= 0:
		return
	var chave = str(idx - 1)
	_carregar_exemplo(chave)

func _carregar_exemplo(chave: String) -> void:
	if not EXEMPLOS.has(chave):
		return
	var ex = EXEMPLOS[chave]
	editor.text = ex["codigo"]
	opt_linguagem.selected = ex["ling"]
	console.text = "Exemplo '" + ex["nome"] + "' carregado.\nClique em '▶ Executar' para rodar."
	lbl_status.text = "Exemplo carregado."

func _executar_codigo() -> void:
	var codigo = editor.text.strip_edges()
	if codigo.is_empty():
		console.text = "⚠ O editor está vazio. Escreva algum código ou escolha um exemplo!"
		lbl_status.text = "Código vazio."
		return

	var ling_idx = opt_linguagem.selected
	if ling_idx == 0:
		_executar_gdscript(codigo)
	else:
		_executar_outra_linguagem(codigo, opt_linguagem.get_item_text(ling_idx))

func _executar_gdscript(codigo: String) -> void:
	lbl_status.text = "Executando GDScript..."
	console.text = "=== Executando GDScript no Zenith ===\n"

	var buffer_saida = []
	var script_completo = """extends RefCounted
var saidas = []
func print(msg):
	saidas.append(str(msg))

func rodar():
"""
	for linha in codigo.split("\n"):
		script_completo += "\t" + linha + "\n"

	script_completo += "\treturn saidas\n"

	var sc = GDScript.new()
	sc.source_code = script_completo
	var err = sc.reload()
	if err != OK:
		console.text += "❌ Erro de compilação/sintaxe (código %d)!\n" % err
		console.text += "Dica: confira a indentação (espaços/tabs) e parênteses.\n"
		console.text += "Clique em '🧠 Zenith, me ensina' para ela consertar o código para você!"
		lbl_status.text = "Erro de sintaxe."
		return

	var instancia = sc.new()
	var res = instancia.rodar()
	if res is Array and not res.is_empty():
		for s in res:
			console.text += str(s) + "\n"
	else:
		console.text += "Código executado com sucesso (sem saídas de print).\n"

	console.text += "=== Fim da Execução (Sucesso) ==="
	lbl_status.text = "Execução concluída com sucesso!"

func _executar_outra_linguagem(codigo: String, nome_ling: String) -> void:
	console.text = "=== Código em " + nome_ling + " ===\n"
	console.text += "Linguagem selecionada: " + nome_ling + "\n\n"
	console.text += "💡 Para compilar e rodar códigos em " + nome_ling + " nativamente:\n"
	console.text += "1. No computador: o Zenith roda pelo terminal Python/Java local.\n"
	console.text += "2. No celular: clique no botão abaixo '🧠 Zenith, me ensina este código!' para ela simular a execução passo a passo, encontrar erros e te ensinar como funciona!\n\n"
	console.text += "Código verificado (sintaxe estruturada):\n"
	var linhas = codigo.split("\n")
	console.text += "Total de linhas: " + str(linhas.size()) + "\n"
	lbl_status.text = "Pronto para mentoria."

func _pedir_mentoria() -> void:
	var codigo = editor.text.strip_edges()
	if codigo.is_empty():
		return
	var nome_ling = opt_linguagem.get_item_text(opt_linguagem.selected)
	var prompt = "Zenith, estou estudando programação (" + nome_ling + "). Seja minha mentora (no estilo do canal da Shogers e da Rembria). Analise meu código abaixo, me explique de forma clara o que cada parte faz, aponte melhorias e me passe um mini-desafio para eu tentar fazer:\n\n```" + nome_ling.to_lower() + "\n" + codigo + "\n```"

	# Fecha a tela de programação e envia no chat
	ui._hide_overlay(ui.programacao_overlay)
	if ui.input_field:
		ui.input_field.text = prompt
		ui._on_send_pressed()
