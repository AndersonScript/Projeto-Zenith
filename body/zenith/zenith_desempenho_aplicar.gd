extends RefCounted
# ============================================================
#  ZENITH — aplica no Corpo o que o downgrade escolheu (v1.11, port celular).
#
#  O Cérebro manda {"action":"desempenho_config","recursos":{...}} ao conectar e a cada "Aplicar". Aqui o Corpo faz a
#  parte DELE: limitar os quadros por segundo, a qualidade gráfica e TROCAR O AVATAR (v1.17: "padrao" = avatar simples
#  low-poly, zenith_avatar_simples.gd; "vrm" = o VRM de sempre). (Voz, microfone, câmera, IA local e memória são do
#  Cérebro; ele mesmo cuida delas.)
#
#  NÃO FOI EXECUTADO NO GODOT. A qualidade usa a escala 3D e o MSAA da janela principal; no renderizador Compatibility
#  (o do Zenith) a escala 3D pode ter pouco ou nenhum efeito — confira ao testar. Os FPS têm efeito garantido.
# ============================================================

const ESCALA := {"alta": 1.0, "media": 0.8, "baixa": 0.6}

func aplicar(d: Dictionary, arvore: SceneTree) -> void:
	var recursos: Dictionary = d.get("recursos", {})
	if recursos.has("fps"):
		Engine.max_fps = int(recursos["fps"])
	if recursos.has("avatar") and arvore != null:
		var corpo = arvore.current_scene                  # a raiz do Corpo (akira_body.gd)
		if corpo != null and corpo.has_method("usar_avatar_simples"):
			var erro: String = corpo.usar_avatar_simples(str(recursos["avatar"]) == "padrao")
			if erro != "":
				push_warning("[Zenith/Desempenho] Avatar: " + erro)
	var qualidade := str(recursos.get("qualidade_grafica", ""))
	if ESCALA.has(qualidade) and arvore != null and arvore.root != null:
		var janela = arvore.root
		janela.scaling_3d_scale = float(ESCALA[qualidade])
		if qualidade == "alta":
			janela.msaa_3d = Viewport.MSAA_2X
		else:
			janela.msaa_3d = Viewport.MSAA_DISABLED
