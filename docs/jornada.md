# Jornada e dependências

Execute em ordem **00–09 → 15–16 → 99** na mesma conta e região.

| Aulas | Dependência e resultado |
|---|---|
| 00 | Identifica a sessão e inicia ou retoma o registro da execução |
| 01 | Cria Cognito, Lambda e Gateway; valida MCP autenticado |
| 02–03 | Reutiliza 01; compara audiências e cria Runtime com identidade própria |
| 04–05 | Acrescenta Cedar, geração e revisão de políticas |
| 06–08 | Cria Registry e personas; testa aprovação, descoberta e execução |
| 09 | Integra os recursos anteriores |
| 15 | Cria fonte sintética, ACL e eventos Memory |
| 16 | Cria RAG MANAGED e valida recuperação autorizada |
| 99 | Remove os recursos registrados da execução |

Cada criação grava os identificadores em `.workshop/`. Não apague esse registro
para reiniciar. Uma execução encerrada por 99 permite que 00 arquive o histórico
e gere novos nomes. Veja [limpeza e retomada](cleanup.md).

13–14 e 90–92 são referências sem código. A01–A04 são independentes da jornada;
use o kernel e as rotinas de limpeza dos próprios extras.
