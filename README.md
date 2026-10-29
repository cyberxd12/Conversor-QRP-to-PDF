# Conversor QRP para PDF em Massa (Desktop)

Sistema desktop moderno desenvolvido com **CustomTkinter** e Python para conversão em lote de relatórios QuickReport (`.QRP`) diretamente para arquivos `.PDF`, salvando automaticamente na mesma pasta de origem de cada arquivo.

---

## 📥 Download do Executável Pronto (.exe)

Não precisa instalar o Python! Você pode baixar a versão já compilada para Windows diretamente na página de Releases:

👉 **[Baixar ConversorQRP.exe (atualizado)](https://github.com/cyberxd12/Conversor-QRP-to-PDF/releases/tag/v1.0.0)**

Basta baixar o arquivo `.exe` e executar.

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

## 📦 Como Gerar o Executável Standalone (.exe)

Caso queira compilar o executável por conta própria:

### Opção 1: Compilação Local
Dê um duplo clique no script `compilar_executavel.bat`. O arquivo será gerado em `dist\ConversorQRP.exe`.

### Opção 2: Versão Pré-Compilada (GitHub Releases)
O executável já compilado está disponível em: [Git Release](https://github.com/cyberxd12/Conversor-QRP-to-PDF/releases/tag/v1.0.0).

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
