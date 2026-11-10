# Onde está cada documento (Mapa do Zenith)

Toda a documentação técnica, histórico de decisões, guias de teste, publicação e robótica foi unificada em **um único documento mestre**:

- **[`docs/MANUAL_GERAL_ZENITH.md`](MANUAL_GERAL_ZENITH.md)** — **O Manual Geral Completo** (arquitetura, decisões de engenharia, Controle Inteligente, APIs grátis, carrinho ESP32-S3 + Uno, roteiro de testes e publicação no GitHub/Vercel).

## Documentos Oficiais e de Sistema (Mantidos)
| Arquivo | Para que serve |
|---|---|
| `docs/MANUAL_GERAL_ZENITH.md` | **Documento único consolidado** com tudo sobre o projeto |
| `docs/Projeto_Zenith_Documento_Conceitual_2.0.docx` | Especificação Conceitual em Word (gerada por `tools/gerar_documentos.py` a partir de `docs/interno/documentos/DOCUMENTO_DO_PROJETO.md`) |
| `docs/Historico_de_Mudancas_Zenith.docx` | Histórico de Mudanças em Word (gerado a partir de `docs/interno/documentos/HISTORICO_DE_MUDANCAS.md`) |
| `docs/RENOMEAR_INTERNOS_GODOT.md` | Guia rápido para renomear nós internos no editor do Godot (usado por `tools/preparar_publico.py`) |
| `BIBLIA_ZENITH.md` | Regras da IA geradas automaticamente a partir de `brain/zenith_biblia.py` |
| `NOTES_ANTIVIRUS.md` | Guia detalhado sobre Controle Inteligente de Aplicativos e antivírus |
| `firmware/LEIA-ME.md` | Mapa de pinos e gravação do ESP32-S3 e Arduino Uno |
