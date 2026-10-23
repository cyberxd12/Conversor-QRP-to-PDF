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

---

## 📦 Como Gerar o Executável Standalone (.exe)

### Opção 1: Compilação Automática no GitHub (Releases)
O repositório possui uma **GitHub Action** configurada em `.github/workflows/build-release.yml` que compila o executável automaticamente e anexa na aba **Releases** do GitHub:

1. **Via Git Tag**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
2. **Manualmente pela interface do GitHub**:
   - Vá na aba **Actions** no GitHub.
   - Selecione a workflow **"Build e Criar Release"**.
   - Clique em **"Run workflow"** e informe a versão desejada.

Ao finalizar, a Action disponibiliza:
- `ConversorQRP.exe` (Executável direto)
- `ConversorQRP-Windows-x64.zip` (Pacote zip com executável e documentação)

### Opção 2: Compilação Local
Dê um duplo clique no script [compilar_executavel.bat](file:///c:/Users/luis.suporte/Documents/programação/conversor/compilar_executavel.bat). O arquivo será gerado em `dist\ConversorQRP.exe`.

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
