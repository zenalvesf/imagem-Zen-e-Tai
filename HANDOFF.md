# HANDOFF — Tradutor de Voz

> Documento de passagem de bastão do mini-app **Tradutor de Voz**, construído como
> artefato do Claude e versionado aqui para não se perder.

- **Artefato publicado (privado do dono):** https://claude.ai/artifact/7EoNKcGqM1G5CGxxoEB5Xw
- **Código-fonte no repo:** [`tradutor-de-voz/tradutor-de-voz.html`](tradutor-de-voz/tradutor-de-voz.html)
- **Versão publicada atual:** v5
- **Data desta passagem:** 2026-11-23

---

## 1. Objetivo

Um tradutor de voz para **conversar frente a frente com pessoas de outros países**:
cada pessoa fala no seu idioma, o app reconhece, traduz nas duas direções e **lê a
tradução em voz alta** para a outra pessoa ouvir. Também tem um modo simples de
traduzir um texto avulso.

## 2. O que foi feito

Página única (HTML/CSS/JS, sem framework) publicada como artefato, com duas abas:

**Aba Conversa (principal)**
- Reconhecimento de voz por pessoa (dois botões, um por idioma) + tradução + leitura em voz alta.
- **Mãos livres:** o microfone segue ouvindo frase após frase; pausa automaticamente
  enquanto fala a tradução (evita eco) e retoma sozinho.
- **Detectar idioma:** um botão só; o Claude decide quem falou qual idioma e traduz para o outro.
- **Velocidade da voz** (0,6×–1,4×).
- **Escolha de voz** por idioma (quando o dispositivo tem mais de uma voz).
- **Várias conversas** salvas (seletor + nova + apagar), cada uma com seus idiomas/nomes/histórico.
- **Nomes dos participantes** (aparecem nos balões e na exportação).
- **Copiar conversa** como texto.
- **Campo de texto** como alternativa quando não há microfone.

**Aba Traduzir**
- Texto → tradução, com voz de entrada (mic) e saída, copiar, inverter idiomas.
- **Traduzir enquanto digito** (debounce, sem falar em voz alta automaticamente).

**Persistência**
- Histórico e preferências salvos localmente (`localStorage`) **e** sincronizados na conta
  do usuário via capacidade `db` (um documento por conversa em `data/users/<id>/convos`),
  o que permite retomar em outro dispositivo. Indicador de status de sincronização na tela.

**Idiomas suportados:** pt, en, es, fr, de, it, ja, ko, zh, ru, ar, hi, nl.

## 3. Decisões técnicas

- **Artefato do Claude** em vez de app hospedado: entrega imediata, sem backend próprio.
- **Tradução via capacidade `sample`** (o próprio Claude traduz dentro da página) — sem
  chave de API nem serviço externo.
- **Voz** com as APIs nativas do navegador: `SpeechRecognition` (entrada) e
  `speechSynthesis` (saída). Sem dependências externas.
- **Capacidades declaradas:** `sample` (tradução), `db` + `user` (histórico sincronizado e privado por conta).
- **Privacidade:** histórico em `data/users/<id>/…`, privado por conta; o artefato é privado do dono.
- **Degradação graciosa:** se `sample`/`db` não estiverem disponíveis, cai para modo local
  e mostra avisos em vez de quebrar.
- **Anti-eco em mãos livres:** o reconhecimento é suspenso durante a fala da tradução e
  retomado no fim.

## 4. Estado atual

- ✅ Publicado (v5) e funcional pelo design; abre nas duas abas.
- ✅ Verificado **localmente** (navegador headless): JavaScript sem erros de sintaxe,
  interface monta nas duas abas, sem erros de console (só um `favicon.ico` 404 irrelevante).
- ⏳ **Ainda não testado ao vivo pelo usuário.** Teste real de tradução, voz e sincronização
  depende do navegador/sessão logada e estava **agendado para o Chrome** pelo usuário.
- Não foi possível testar o fluxo ao vivo do lado do assistente: tradução (`sample`) e
  sincronização (`db`) só rodam dentro do runtime do claude.ai, logado.

## 5. Limitações conhecidas

- **Firefox não tem reconhecimento de voz** (entrada por microfone). Nele, use a digitação;
  a leitura em voz alta funciona. **Chrome é o recomendado** para voz.
- A **lista de vozes depende do dispositivo**: em alguns aparelhos há só uma voz por idioma
  (aí o seletor de voz fica oculto).
- **Detecção de idioma na fala:** é confiável no texto, mas o reconhecimento de voz do
  navegador precisa de um idioma por vez — usa-se como base o último idioma detectado.
  Para pares de idiomas parecidos, os botões por pessoa são mais precisos.
- O microfone pode ser bloqueado dentro do preview por permissão do navegador.

## 6. Próximos passos

1. **Teste ao vivo no Chrome (logado):** confirmar tradução, leitura em voz alta e o
   indicador "☁️ Sincronizado"; idealmente abrir em um segundo dispositivo para ver o
   histórico sincronizar.
2. Ajustar conforme o retorno do teste (ex.: permissão de microfone, voz que não sai,
   sincronização travada).
3. Ideias ainda não feitas, se houver interesse:
   - Botão de **compartilhar** uma conversa específica.
   - **Exportar** a conversa como arquivo (`downloads`).
   - Escolha de **tom/pitch** da voz, além da velocidade.

## 7. Como editar

O código-fonte está em `tradutor-de-voz/tradutor-de-voz.html`. Para atualizar o artefato
publicado, republique esse arquivo no mesmo URL do artefato (v5 acima). O arquivo é
autocontido (o Claude envolve o conteúdo num documento HTML completo ao publicar).
