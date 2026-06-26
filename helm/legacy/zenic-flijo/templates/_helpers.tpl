{{- define "zenic-flijo.name" -}}
{{- default .Chart.Name .Values.app.name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zenic-flijo.fullname" -}}
{{- $name := default .Chart.Name .Values.app.name }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "zenic-flijo.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zenic-flijo.secretname" -}}
{{- printf "%s-secrets" (include "zenic-flijo.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zenic-flijo.databaseUrl" -}}
{{- $host := include "zenic-flijo.postgresHost" . }}
{{- $db := .Values.postgresql.auth.database }}
{{- $user := .Values.postgresql.auth.username }}
{{- printf "postgresql+psycopg://%s:****@%s:5432/%s" $user $host $db }}
{{- end }}

{{- define "zenic-flijo.redisUrl" -}}
{{- $host := include "zenic-flijo.redisHost" . }}
{{- printf "redis://:%s@%s:6379/0" .Values.redis.auth.password $host }}
{{- end }}

{{- define "zenic-flijo.postgresHost" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql.%s.svc.cluster.local" .Release.Name .Release.Namespace }}
{{- else }}
{{- .Values.postgresql.externalHost | default "postgres" }}
{{- end }}
{{- end }}

{{- define "zenic-flijo.redisHost" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis-master.%s.svc.cluster.local" .Release.Name .Release.Namespace }}
{{- else }}
{{- .Values.redis.externalHost | default "redis" }}
{{- end }}
{{- end }}

{{- define "zenic-flijo.postgresSecret" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" .Release.Name }}
{{- else }}
{{- printf "%s-external-postgres" (include "zenic-flijo.fullname" .) }}
{{- end }}
{{- end }}

{{- define "zenic-flijo.redisSecret" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis" .Release.Name }}
{{- else }}
{{- printf "%s-external-redis" (include "zenic-flijo.fullname" .) }}
{{- end }}
{{- end }}
