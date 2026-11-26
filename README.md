Integrantes: **Grupo NGA**
Arthur Henrique Longo - 2025116860
Gabriel Falavena Oliveira - 2025116965
Nicolas Maciel de Souza - 2025116314


# Radar do Almoço

Protótipo para o **Hackathon FMU Tech 2026.2**, desenvolvido para o almoço por quilo da **Bovinu’S Grill & Beer — Unidade Augusta**.

## Problema

Durante o almoço, o cliente se serve, pode passar pela churrasqueira, pesa o prato e escolhe uma mesa. A Bovinu’S apontou o tempo de espera como uma das dores da operação. Nos dois vídeos de apoio, há uma concentração de clientes junto a um dos balcões por volta das 13h06. O trecho motiva medir a espera por estação. A duração e a causa dessa concentração ainda precisam ser medidas no local. [Materiais oficiais do desafio](https://grupobovinus-my.sharepoint.com/:f:/g/personal/gabriel_chiesa_grupobovinus_com_br/IgCYmK122fcmQ44gTxgKRCqcAfftZ0bLPJaC3tYg7DfoMOw?e=QWw2bL)

## Solução

O operador registra a chegada ao **buffet**, à **churrasqueira** ou à **balança**. Quando o atendimento começa, ele encerra a medição. Se o cliente sair antes, o operador registra a saída. O painel da gerência atualiza a cada cinco segundos e destaca as estações com espera acima do limite.

| Indicador | Como é calculado |
| --- | --- |
| Em espera | Registros da estação que ainda não começaram o atendimento nem saíram da fila. |
| Maior espera | Tempo desde a chegada da senha mais antiga que ainda está na fila. |
| Mediana em 15 min | Mediana dos tempos de espera dos atendimentos iniciados nos últimos 15 minutos. |
| Espera extra acumulada | Soma dos segundos acima do limite para as senhas que ainda esperam. |
| Atendimentos acima do limite | Quantos dos atendimentos iniciados nos últimos 15 minutos esperaram mais que o limite da estação. Serve de base para a proporção de esperas acima do limite no piloto. |
| Saídas antes do atendimento | Total de saídas registradas nas três estações nos últimos 15 minutos. |

Cada alerta indica uma ação que o gerente pode testar. Na churrasqueira, uma opção é deslocar apoio para o corte. O registro manual produz uma amostra da fila. Uma mesma pessoa pode aparecer em mais de uma estação, por isso os totais representam registros.

## Impacto e validação

O restaurante informa cerca de **618 clientes por dia**, consumo médio de **482 g por cliente durante a semana** e preço de **R$ 119,90/kg**. O valor de **R$ 57,79** no alerta é um cenário hipotético de venda potencial se um cliente desistisse de comprar um prato de 482 g. Uma saída registrada significa que o cliente deixou aquela fila. Para concluir que houve perda de venda, seria preciso acompanhar o restante da jornada.

Em um piloto, a equipe pode comparar a mediana e a proporção de esperas acima do limite antes e depois de uma intervenção. A comparação deve usar faixas de horário e critérios de amostragem semelhantes. As saídas anteriores ao atendimento podem ser comparadas separadamente.

## Arquitetura

| Componente | Responsabilidade |
| --- | --- |
| `templates/`, `static/` | Telas responsivas de operação e gerência em HTML, CSS e JavaScript. |
| `app.py` | Servidor HTTP da biblioteca padrão do Python. Recebe registros, consulta o estado da fila e calcula os indicadores. |
| `schema.sql`, `instance/` | Estrutura SQLite e bancos locais de operação e demonstração. A pasta `instance/` é criada na primeira execução. |
| `/api/export.csv` | Exporta todos os registros (senha, estação, chegada, início, saída, situação e espera em segundos) com separador `;`, para abrir direto no Excel e comparar antes e depois no piloto. |
| `demo/scenario.json` | Parâmetros do cenário simulado de 13h06. A duração da faixa de almoço e as proporções da amostra são premissas da simulação. |

O navegador envia as ações ao servidor, que grava a transição da senha no SQLite. O painel consulta o estado consolidado e avalia o limite por estação. O MVP usa senhas internas e registro manual. A leitura dos códigos dos cartões físicos pode ser avaliada em um piloto com acesso ao sistema atual.

## Como rodar

Use **Python 3.10 ou mais recente**. Abra o terminal na pasta do projeto e execute:

```powershell
python app.py --demo
```

Abra o [painel gerencial](http://127.0.0.1:8000/) e a [tela de operação](http://127.0.0.1:8000/operacao) em abas separadas. O cenário começa com o relógio pausado às **13h06**. Use **Avançar 1 min** para simular a passagem do tempo ou **⋯ → Restaurar demo das 13h06** para voltar ao estado inicial.

Para exportar os dados, use **⋯ → Exportar registros (CSV)** no painel. Para registrar um piloto local em um banco separado, execute `python app.py`, sem `--demo`. A aplicação escuta no próprio computador por padrão. Caso a porta 8000 esteja ocupada, use `--port 8001` e abra as telas nessa porta.

Execute `python -m unittest -v` para rodar os 9 testes: migração do banco, cenário de gravação, saída da fila, concorrência, validação de entradas e limites, exportação CSV e as rotas HTTP. O projeto não tem dependências externas.

## Demonstração e apresentação

- [Roteiro de gravação de até dois minutos](docs/roteiro-video.md)
- **Vídeo da demonstração** — link a incluir após a gravação e a publicação.
- [Apresentação em cinco slides](docs/apresentacao.html) — abra o arquivo no navegador e use as setas para avançar.
- [Roteiro do pitch de até quatro minutos](docs/pitch.md)
- **Capturas da solução** — previstas para a versão final do repositório, com até cinco imagens.

## Segurança e limites do protótipo

- A aplicação escuta apenas em `127.0.0.1` por padrão. Ao usar `--host 0.0.0.0` para que tablets da equipe acessem pela rede do restaurante, lembre que **não há autenticação**: use uma rede interna e confiável.
- As respostas incluem cabeçalhos de segurança (CSP, `nosniff`, `no-store`), e as entradas de todas as rotas de escrita são validadas no servidor.
- `GET /api/health` responde se o servidor está no ar e em qual modo.
