{{- define "ranks.name" -}}
{{- default .Chart.Name .Values.ranks.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ranks.fullname" -}}
{{- if .Values.ranks.fullnameOverride -}}
{{- .Values.ranks.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.ranks.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ranks.labels" -}}
app.kubernetes.io/name: {{ include "ranks.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
