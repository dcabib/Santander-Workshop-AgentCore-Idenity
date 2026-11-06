# Ciclo em contas efêmeras

1. Prepare o kernel e a sessão conforme [preparação](preparacao.md).
2. Execute 00 e confira a conta, região, principal e modo NEW/RESUME.
3. Siga [a jornada](jornada.md), guardando outputs e Request IDs sem segredos.
4. Execute 99 antes do encerramento da conta e confira o estado CLEANED.

Na próxima conta, prepare uma sessão nova e execute novamente a criação.
`.workshop/` separa registros por conta e região; não reutilize IDs de outra
conta. Uma sessão expirada precisa ser renovada antes da limpeza. A validade
das credenciais não garante que recursos remanescentes tenham sido removidos.

Não altere recursos protegidos ou compartilhados do evento. Os extras encerram
seus próprios recursos; 99 administra somente a jornada registrada.
