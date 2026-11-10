# Renomear os nomes internos do Godot (tarefa para quem tem o editor)

O nome visível da IA já é **Zenith** em tudo que o usuário vê. Sobraram nomes **internos** (arquivos e nós do Godot)
com o nome antigo. Ninguém vê isso, mas dá para limpar — **só pelo editor do Godot**, porque o editor atualiza as
referências sozinho (editar o texto na mão quebra a cena).

| Hoje | Vira | Onde |
|---|---|---|
| `addons/avatars/Akira.vrm` | `Zenith.vrm` (ou o seu modelo) | FileSystem do Godot > botão direito > Renomear |
| `addons/vrm/node_constraint/icons/Akira_Body.tscn` | `Zenith_Body.tscn` | idem (o editor ajusta `project.godot`) |
| nó `Akira` dentro dessa cena | `Zenith` | painel Scene > F2 |
| `akira_body.gd`, `akira_vida.gd` | `zenith_body.gd`, `zenith_vida.gd` | idem — depois atualize os testes que citam esses nomes |
| `get_node_or_null("Akira")` (9 lugares em `zenith_body.gd`) | `"Zenith"` | busca e troca |

Depois: rode `python -m unittest discover -s tests -t .` (alguns testes leem esses arquivos pelo nome — troque o nome
neles também), exporte o Corpo e confira que o avatar aparece. Quando terminar, `tools/preparar_publico.py` não vai mais
mostrar o aviso de "referências internas".
