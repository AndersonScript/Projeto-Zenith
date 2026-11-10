extends Node
# ============================================================
#  ZENITH — vrm_runtime_bootstrap.gd
#
#  CORREÇÃO (caretas/blendshapes não ativam após trocar o VRM):
#  addons/vrm/plugin.gd registra as extensões VRM do GLTFDocument
#  (VRMC_vrm, spring bones, material MToon, node constraints) — mas
#  ele é um EditorPlugin, e o PRÓPRIO CÓDIGO DO ADDON já avisa:
#  "This editor plugin script won't run outside of the editor."
#
#  Ou seja: quando o Corpo troca o VRM em tempo de execução via
#  akira_body.gd -> reload_vrm() (GLTFDocument.append_from_file),
#  nenhuma dessas extensões estava registrada — o GLTFDocument carregava
#  o glTF "cru", sem o remapeamento de ossos humanoides, sem a conversão
#  de material MToon, e sem os nomes de blend shape que o addon normaliza
#  (é por isso que find_blend_shape_by_name("Blink"/"Joy"/...) não achava
#  nada depois de um reload em runtime).
#
#  Este script faz, na inicialização do jogo, exatamente o mesmo
#  registro que plugin.gd faz no editor — só que válido também dentro
#  do .exe exportado. Precisa ser um Autoload (Singleton), configurado
#  em Project > Project Settings > Autoload, pra rodar ANTES de
#  qualquer VRM ser carregado (inclusive o inicial, na cena principal).
# ============================================================

const VRMC_node_constraint = preload("./1.0/VRMC_node_constraint.gd")
const VRMC_springBone = preload("./1.0/VRMC_springBone.gd")
const VRMC_materials_mtoon = preload("./1.0/VRMC_materials_mtoon.gd")
const VRMC_materials_hdr_emissiveMultiplier = preload("./1.0/VRMC_materials_hdr_emissiveMultiplier.gd")
const VRMC_vrm = preload("./1.0/VRMC_vrm.gd")

var _vrm_inst := VRMC_vrm.new()
var _node_constraint_inst := VRMC_node_constraint.new()
var _spring_bone_inst := VRMC_springBone.new()
var _mtoon_inst := VRMC_materials_mtoon.new()
var _hdr_emissive_inst := VRMC_materials_hdr_emissiveMultiplier.new()

var _registered := false

func _ready():
	# Idempotente: se rodar dentro do editor (onde plugin.gd já
	# registrou as mesmas extensões), registrar de novo daria erro —
	# então só registra fora do editor, ou se ainda não registrado.
	if Engine.is_editor_hint():
		return
	_register_all()

func _register_all():
	if _registered:
		return
	GLTFDocument.register_gltf_document_extension(_vrm_inst)
	GLTFDocument.register_gltf_document_extension(_node_constraint_inst)
	GLTFDocument.register_gltf_document_extension(_spring_bone_inst)
	GLTFDocument.register_gltf_document_extension(_hdr_emissive_inst)
	GLTFDocument.register_gltf_document_extension(_mtoon_inst)
	_registered = true
	print("[Zenith/Corpo] Extensões VRM registradas em runtime (troca de VRM ao vivo agora preserva ossos humanoides, material MToon e blend shapes).")

func _exit_tree():
	if not _registered:
		return
	GLTFDocument.unregister_gltf_document_extension(_vrm_inst)
	GLTFDocument.unregister_gltf_document_extension(_node_constraint_inst)
	GLTFDocument.unregister_gltf_document_extension(_spring_bone_inst)
	GLTFDocument.unregister_gltf_document_extension(_mtoon_inst)
	GLTFDocument.unregister_gltf_document_extension(_hdr_emissive_inst)
	_registered = false
