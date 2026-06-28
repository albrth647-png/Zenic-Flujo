{{- /*
Zenic-Flijo — Helm Helper Templates
*/}}

{{- define "zenic-flujo.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zenic-flujo.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "zenic-flujo.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "zenic-flujo.labels" -}}
helm.sh/chart: {{ include "zenic-flujo.chart" . }}
{{ include "zenic-flujo.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "zenic-flujo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zenic-flujo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "zenic-flujo.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "zenic-flujo.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "zenic-flujo.postgresUrl" -}}
{{- $pg := .Values.externalServices.postgres -}}
{{- if $pg.existingSecret -}}
postgresql://$(PG_USER):$(PG_PASSWORD)@{{ $pg.host }}:{{ $pg.port }}/{{ $pg.database }}
{{- else -}}
{{- printf "postgresql://%s:%s@%s:%d/%s" $pg.user $pg.password $pg.host $pg.port $pg.database -}}
{{- end -}}
{{- end -}}

{{- define "zenic-flujo.redisUrl" -}}
{{- $r := .Values.externalServices.redis -}}
redis://{{ $r.host }}:{{ $r.port }}/0
{{- end -}}
