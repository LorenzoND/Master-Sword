# Master-Sword

Ferramenta nativa (Windows, sem browser) pra controlar e monitorar CPU + GPU em notebooks com
gargalo térmico — substitui o combo manual de `nvidia-smi -lgc` + ThrottleStop por um dashboard
único, leve, com gráficos ao vivo, overlay opcional e perfis de um clique.

Desenvolvida pra um MSI GS66 Stealth 10SE (Intel i7-10750H + RTX 2060), mas o core (GPU NVIDIA
via NVML, CPU Intel via Power Plan) funciona em qualquer notebook com essa combinação.

## Funcionalidades

- **GPU**: leitura completa (temp, clocks, power, VRAM, utilização, processos por PID), lock de
  clock (equivalente a `nvidia-smi -lgc`)
- **CPU**: toggle de Boost/Turbo via Power Plan do Windows (sem precisar de driver nem admin),
  sensores completos (temp/clock/power) via LibreHardwareMonitor + PawnIO
- **Perfis**: salva combinações de config (clock da GPU + boost da CPU) e aplica tudo com 1 clique
- **Dashboard**: gráficos ao vivo (ImPlot) de temperatura, clock e power
- **Overlay**: janela compacta, sempre no topo, liga/desliga pela bandeja
- **Varredura de processos**: lista o que mais consome CPU/RAM/GPU, com ação de baixar prioridade
  (reversível, estilo Process Lasso) ou encerrar (`kill`, sempre manual com confirmação)

## Rodar

Requer Python 3.12+, Windows, GPU NVIDIA e CPU Intel.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Lock de clock/power da GPU e sensores completos de CPU exigem rodar como administrador — use
`setup_shortcut.ps1` pra criar um atalho na área de trabalho que já abre elevado:

```
powershell -ExecutionPolicy Bypass -File setup_shortcut.ps1
```

(O atalho eleva o `powershell.exe`, não o `python.exe` direto — o SmartScreen bloqueia elevação
de binários novos/sem reputação, então a saída é elevar um binário confiável e chamar o Python
como processo filho já dentro da sessão elevada.)

Sensores completos de CPU (temperatura, clock, power) também precisam do driver
[PawnIO](https://github.com/namazso/PawnIO) instalado (`winget install PawnIO`) — sem ele, só o
`%` de uso de CPU fica disponível.

## Estrutura

```
core/
  gpu_control.py    NVML: leitura + lock de clock + power limit + processos por GPU
  cpu_control.py    powercfg (boost) + LibreHardwareMonitor (sensores)
  scan.py           varredura de processos (CPU/RAM/GPU) + baixar prioridade / kill
  profiles.py       perfis salvos em profiles/*.json
  live_state.py     estado compartilhado entre o dashboard e o overlay (processo separado)

ui/
  dashboard.py       janela principal
  tray.py            ícone na bandeja
  overlay.py         overlay compacto, always-on-top (subprocesso)
  process_window.py  janela de varredura de processos
  theme.py            tema visual
  icon.py             ícone pixel-art (gerado uma vez, cacheado em assets/)
```

## Limitações conhecidas

- Overlay não é transparente/clickthrough — a versão atual do Dear PyGui não expõe essas funções
  de viewport ainda
- Power limit da GPU costuma vir travado pelo vBIOS em notebook (`NotSupported` via NVML) —
  lock de clock funciona normalmente
- Controle de fan (EC do notebook) ainda não implementado
