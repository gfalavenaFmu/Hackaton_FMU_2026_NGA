# Pitch de até 4 minutos

Abra a [apresentação](apresentacao.html), o painel e a operação em três abas. Para a demonstração ao vivo, restaure o cenário das **13h06**, selecione **Churrasqueira** na operação e mantenha o relógio pausado. Os tempos abaixo são marcas de ensaio. Procure encerrar em **3min50s**.

### 0:00–0:30 · Slide 1 — Radar do Almoço

“No pico do almoço, quando muita gente se concentra perto do buffet, onde o gerente deveria colocar mais uma pessoa da equipe? Na churrasqueira, na balança ou na reposição dos balcões? O Radar do Almoço foi feito para responder essa pergunta com registros de espera por estação. Nosso recorte é o almoço por quilo da Bovinu’S Augusta.”

### 0:30–1:15 · Slide 2 — Uma fila que ainda precisa ser medida

“O restaurante informa cerca de 618 clientes por dia. Cruzamos o mapa da casa com a comanda física e os dois vídeos da operação. Por volta das 13h06, os dois ângulos mostram mais pessoas se servindo e uma concentração junto a um balcão. As imagens ajudam a escolher onde observar. Para saber quanto o cliente esperou e em qual etapa, precisamos medir a chegada e o início do atendimento. Como o percurso passa por pontos diferentes, contar só a fila total deixaria o gerente sem saber onde testar uma intervenção.”

### 1:15–1:57 · Slide 3 — Da senha ao painel

“Transformamos esse percurso em três estações no protótipo. Na tela de operação, o funcionário registra a chegada e depois marca o início do atendimento ou uma saída da fila. O servidor em Python grava cada etapa no SQLite. O painel mostra a maior espera, a mediana dos últimos quinze minutos e quantas senhas passaram do limite daquela estação. A proposta é usar o painel para decidir onde concentrar o apoio. A primeira versão funciona por amostragem, com senhas internas.”

### 1:57–3:05 · Slide 4 — Alerta na churrasqueira

**Ação ao vivo:** mostre o alerta no painel. Em operação, registre uma nova chegada na churrasqueira e inicie o atendimento das cinco senhas mais antigas, uma por vez. Volte ao painel e dê até cinco segundos para a atualização. Se a troca de abas falhar, continue no slide com o antes e depois da simulação.

“Aqui temos a simulação das 13h06, com o relógio pausado. A churrasqueira tem oito senhas em espera e cinco passaram do limite de quatro minutos. A sugestão é deslocar apoio para o corte. Vou registrar uma chegada. Agora simulo o início do atendimento para as cinco senhas mais antigas.”

**Ao voltar ao painel:** “O painel agora mostra quatro senhas em espera e nenhuma estação em alerta. Esse é o resultado das ações que acabamos de registrar no cenário simulado. No restaurante, o painel permitiria verificar o que acontece depois de uma intervenção real.”

### 3:05–3:50 · Slide 5 — Piloto no horário de pico

“Ao preço da Augusta, um prato de 482 gramas vale 57 reais e 79 centavos. Esse número ilustra a venda potencial caso uma pessoa desista de comprar. Uma saída da fila, por si só, ainda pode terminar em uma compra. Para validar a proposta, começaríamos pela churrasqueira no horário de pico. Mediríamos a espera antes da intervenção, testaríamos apoio para o corte em uma faixa comparável e observaríamos a mediana, a proporção de esperas acima do limite e as saídas. Assim, a gerência consegue decidir se vale repetir a intervenção no próximo almoço. Obrigado.”

**3:50–4:00:** margem para pausas ou atualização do painel.
