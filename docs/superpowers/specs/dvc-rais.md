# Verificação das tabelas salariais

A origem dos dois artefatos da RAIS rastreados pelo DVC será o repositório DagsHub da equipe. O GitHub Actions recebe a URL pelo repositório e usa credenciais de leitura apenas na etapa de download. A checagem roda na branch principal quando mudam entradas, código ou dependências da agregação e também por disparo manual.

O job baixa os artefatos rastreados, regenera as tabelas de 2025 e falha se o resultado divergir dos arquivos versionados. O aceite em produção depende do envio dos hashes já rastreados e de um download bem-sucedido a partir de um checkout limpo.
