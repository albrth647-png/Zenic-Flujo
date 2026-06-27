import { useEffect, useState, useCallback } from "react"
import { useBpmn } from "@/hooks/useBpmn"
import type { BPMNProcessSummary, BPMNProcess } from "@/types/bpmn"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Upload, Download, Repeat, Trash2, CheckCircle, XCircle, Loader2,
} from "lucide-react"

export default function BpmnPage() {
  const api = useBpmn()
  const [processes, setProcesses] = useState<BPMNProcessSummary[]>([])
  const [selectedProcess, setSelectedProcess] = useState<BPMNProcess | null>(null)
  const [xmlInput, setXmlInput] = useState("")
  const [validationResult, setValidationResult] = useState<{ valid: boolean; errors: string[] } | null>(null)
  const [importResult, setImportResult] = useState<string | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [showValidate, setShowValidate] = useState(false)

  const loadProcesses = useCallback(async () => {
    const data = await api.listProcesses()
    if (data) setProcesses(data)
  }, [api])

  // eslint-disable-next-line react-hooks/set-state-in-effect -- loadProcesses dispara setState (fetch results), patrón legacy a refactorizar en Fase 6
  useEffect(() => { loadProcesses() }, [loadProcesses])

  const handleImport = async () => {
    if (!xmlInput.trim()) return
    setImportResult(null)
    const result = await api.importBpmn(xmlInput)
    if (result) {
      setImportResult(`✅ Importado: ${result.name} (${result.elements} elementos, ${result.flows} flujos)`)
      setXmlInput("")
      setShowImport(false)
      loadProcesses()
    } else if (api.error) {
      setImportResult(`❌ Error: ${api.error}`)
    }
  }

  const handleValidate = async () => {
    if (!xmlInput.trim()) return
    const result = await api.validate(xmlInput)
    if (result) {
      setValidationResult({
        valid: result.valid,
        errors: result.errors?.map(e => e.message) || [],
      })
    }
  }

  const handleExport = async (processId: string) => {
    const result = await api.exportBpmn(processId)
    if (result) {
      const blob = new Blob([result.bpmn_xml], { type: "text/xml" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url; a.download = `${processId}.bpmn`; a.click()
      URL.revokeObjectURL(url)
    }
  }

  const handleConvert = async (processId: string) => {
    const result = await api.convertToWorkflow(processId)
    if (result) {
      setImportResult(`✅ Convertido a workflow: "${result.name || result.workflow_id}"`)
    }
  }

  const handleDelete = async (processId: string) => {
    if (!confirm("¿Eliminar este proceso BPMN?")) return
    const success = await api.deleteProcess(processId)
    if (success) { loadProcesses(); setSelectedProcess(null) }
  }

  const handleViewDetails = async (processId: string) => {
    const detail = await api.getProcess(processId)
    if (detail) setSelectedProcess(detail)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Procesos BPMN</h1>
          <p className="text-sm text-muted-foreground">Importa, valida y gestiona procesos BPMN 2.0</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { setShowValidate(!showValidate); setShowImport(false) }}>
            <CheckCircle className="size-4 mr-2" /> Validar
          </Button>
          <Button onClick={() => { setShowImport(!showImport); setShowValidate(false) }}>
            <Upload className="size-4 mr-2" /> Importar proceso
          </Button>
        </div>
      </div>

      {/* XML Input panel */}
      {(showImport || showValidate) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{showImport ? "Importar proceso" : "Validar proceso"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="Pega aquí el archivo del proceso (formato BPMN)..."
              className="font-mono text-xs min-h-[200px]"
              value={xmlInput}
              onChange={e => setXmlInput(e.target.value)}
            />
            <div className="flex gap-2">
              {showImport && (
                <Button onClick={handleImport} disabled={api.loading || !xmlInput.trim()}>
                  {api.loading ? <Loader2 className="size-4 mr-2 animate-spin" /> : <Upload className="size-4 mr-2" />}
                  Importar
                </Button>
              )}
              {showValidate && (
                <Button onClick={handleValidate} disabled={api.loading || !xmlInput.trim()} variant="secondary">
                  {api.loading ? <Loader2 className="size-4 mr-2 animate-spin" /> : <CheckCircle className="size-4 mr-2" />}
                  Validar
                </Button>
              )}
              <Button variant="ghost" onClick={() => { setShowImport(false); setShowValidate(false); setValidationResult(null) }}>
                Cancelar
              </Button>
            </div>
            {validationResult && (
              <div className={`p-3 rounded-md text-sm ${validationResult.valid ? "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"}`}>
                {validationResult.valid ? (
                  <p className="flex items-center gap-2"><CheckCircle className="size-4" /> Formato de proceso válido</p>
                ) : (
                  <div className="space-y-1">
                    <p className="flex items-center gap-2"><XCircle className="size-4" /> Errores de validación:</p>
                    <ul className="list-disc pl-5 text-xs">
                      {validationResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {importResult && (
              <div className={`p-3 rounded-md text-sm ${importResult.startsWith("✅") ? "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"}`}>
                {importResult}
              </div>
            )}
            {api.error && !importResult && (
              <p className="text-sm text-destructive">{api.error}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Processes table */}
      <Card>
        <CardHeader><CardTitle>Procesos Importados ({processes.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Elementos</TableHead>
                <TableHead>Flujos</TableHead>
                <TableHead>Start/End</TableHead>
                <TableHead>Tasks</TableHead>
                <TableHead>Gateways</TableHead>
                <TableHead>Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {processes.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No hay procesos BPMN importados.</TableCell></TableRow>
              )}
              {processes.map(p => (
                <TableRow key={p.process_id}>
                  <TableCell className="font-medium">
                    <button onClick={() => handleViewDetails(p.process_id)} className="hover:underline text-left">
                      {p.name || p.process_id}
                    </button>
                  </TableCell>
                  <TableCell>{p.elements}</TableCell>
                  <TableCell>{p.flows}</TableCell>
                  <TableCell>{p.start_events}/{p.end_events}</TableCell>
                  <TableCell>{p.tasks}</TableCell>
                  <TableCell>{p.gateways}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button size="icon" variant="ghost" onClick={() => handleExport(p.process_id)} title="Exportar proceso"><Download className="size-3.5" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => handleConvert(p.process_id)} title="Convertir a flujo de trabajo"><Repeat className="size-3.5" /></Button>
                      <Button size="icon" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => handleDelete(p.process_id)} title="Eliminar"><Trash2 className="size-3.5" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Process detail */}
      {selectedProcess && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{selectedProcess.name || selectedProcess.process_id}</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setSelectedProcess(null)}>Cerrar</Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 text-sm mb-4">
              <div><span className="text-muted-foreground">ID:</span> {selectedProcess.process_id}</div>
              <div><span className="text-muted-foreground">Ejecutable:</span> {selectedProcess.is_executable ? "Sí" : "No"}</div>
              {selectedProcess.version && <div><span className="text-muted-foreground">Versión:</span> {selectedProcess.version}</div>}
              {selectedProcess.documentation && <div className="col-span-2"><span className="text-muted-foreground">Documentación:</span> {selectedProcess.documentation}</div>}
            </div>
            <div className="text-xs text-muted-foreground">
              {Object.keys(selectedProcess.elements || {}).length} elementos · {Object.keys(selectedProcess.flows || {}).length} flujos
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
