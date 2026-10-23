# Conversor QRP para PDF em Massa (Desktop)

Sistema desktop moderno desenvolvido com **CustomTkinter** e Python para conversão em lote de relatórios QuickReport (`.QRP`) diretamente para arquivos `.PDF`, salvando automaticamente na mesma pasta de origem de cada arquivo.

---

## ✨ Principais Funcionalidades

- **Salvamento Automático na Pasta de Origem**: Cada arquivo PDF gerado é gravado exatamente no mesmo diretório do arquivo `.QRP` correspondente.
- **Processamento em Massa**:
  - Seleção de múltiplos arquivos `.QRP` simultaneamente.
  - Seleção de pastas inteiras com busca recursiva opcional em subpastas.
- **Suporte a Documentos Multi-páginas**: Converte relatórios de 1 ou várias páginas sem perda de conteúdo.
- **Qualidade Vetorial Configurável**:
  - `300 DPI` (Alta Qualidade de Impressão - Recomendado)
  - `200 DPI` (Equilibrado)
  - `150 DPI` (Rápido)
- **Interface Moderna (CustomTkinter)**:
  - Alternância entre **Modo Escuro** e **Modo Claro**.
  - Tabela com status em tempo real, tamanho dos arquivos e contagem de páginas.
  - Botões de atalho por item: **"Ver PDF"** (abre no leitor padrão) e **"Pasta"** (abre no Windows Explorer).
  - Barra de progresso dinâmica e contadores estatísticos (Total, Pendentes, Concluídos, Erros).
  - Painel de log detalhado com carimbos de data/hora.
- **Arquitetura Thread-Safe**: Processamento em segundo plano via `threading` e fila thread-safe (`queue.Queue`), garantindo que a interface nunca trave ou congele durante a conversão.

---

## 🚀 Como Executar

### 1. Início Rápido (1 Clique)
Basta dar um duplo clique no arquivo:
```
iniciar.bat
```

### 2. Pelo Terminal (Prompt de Comando ou PowerShell)
```bash
python main.py
```

---

## 📦 Como Gerar um Executável Standalone (.exe)

Para distribuir ou executar o programa em qualquer computador sem precisar ter o Python instalado:

1. Dê um duplo clique no arquivo:
   ```
   compilar_executavel.bat
   ```
2. O executável standalone será gerado em:
   ```
   dist\ConversorQRP.exe
   ```

---

## 📁 Estrutura do Projeto

```
conversor/
├── converter.py              # Motor de parsing de containers QRP e renderização vetorial para PDF
├── gui.py                    # Interface gráfica desktop com CustomTkinter
├── main.py                   # Ponto de entrada do sistema
├── iniciar.bat               # Atalho para inicialização imediata
├── compilar_executavel.bat   # Script para empacotar em .exe com PyInstaller
├── requirements.txt          # Dependências do projeto
└── README.md                 # Documentação completa
```
