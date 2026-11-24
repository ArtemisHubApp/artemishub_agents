# Verificação das tabelas salariais com DVC e S3

O remote padrão do DVC usa `s3://dvc` no DagsHub, com o endpoint S3 registrado em `.dvc/config`. Credenciais nunca são armazenadas no Git. O workflow de dados usa os Secrets `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY`, com acesso de leitura, para baixar o Parquet e o JSON rastreados.

O job também permite execução manual e roda na branch principal quando mudam entradas, código, dependências ou sua própria configuração. Ele regenera os agregados de 2025 e falha se os arquivos gerados divergirem dos versionados.

O aceite de dados reais depende de os dois objetos existirem no remote e de um `dvc pull` bem-sucedido em clone limpo.
