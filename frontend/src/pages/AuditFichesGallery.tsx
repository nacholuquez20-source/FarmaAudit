import React, { useState, useEffect } from "react";
import {
  Container,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Box,
  Chip,
  Typography,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import {
  Download,
  OpenInNew,
  Visibility,
  FilterListOff,
  DateRange,
} from "@mui/icons-material";
import { useAuth } from "../contexts/AuthContext";

interface Ficha {
  id: string;
  sucursal_id: string;
  auditor_nombre: string;
  responsable_desvios: string;
  fecha_auditoria: string;
  url_pdf: string;
  google_drive_id: string;
  desvios_count: number;
  fotos_count: number;
  puntuacion_promedio: number;
}

export default function AuditFichesGallery() {
  const { user } = useAuth();
  const [fiches, setFiches] = useState<Ficha[]>([]);
  const [loading, setLoading] = useState(true);
  const [sucursales, setSucursales] = useState<string[]>([]);

  // Filters
  const [selectedSucursal, setSelectedSucursal] = useState("");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [auditorNombre, setAuditorNombre] = useState("");

  // Pagination
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(12);

  // Detail view
  const [selectedFicha, setSelectedFicha] = useState<Ficha | null>(null);
  const [openDetail, setOpenDetail] = useState(false);

  // Load fiches
  const loadFiches = async () => {
    try {
      setLoading(true);

      const params = new URLSearchParams();
      if (selectedSucursal) params.append("sucursal_id", selectedSucursal);
      if (fechaDesde) params.append("fecha_desde", fechaDesde);
      if (fechaHasta) params.append("fecha_hasta", fechaHasta);
      if (auditorNombre) params.append("auditor_nombre", auditorNombre);
      params.append("limit", limit.toString());
      params.append("offset", (page * limit).toString());

      const response = await fetch(`/api/audit-fiches/list?${params}`);
      const data = await response.json();

      if (data.status === "ok") {
        setFiches(data.data);
      } else {
        console.error("Error fetching fiches:", data);
      }
    } catch (error) {
      console.error("Error loading fiches:", error);
    } finally {
      setLoading(false);
    }
  };

  // Load sucursales list
  const loadSucursales = async () => {
    try {
      const response = await fetch("/api/audit-fiches/sucursales");
      const data = await response.json();

      if (data.status === "ok") {
        setSucursales(data.data);
      }
    } catch (error) {
      console.error("Error loading sucursales:", error);
    }
  };

  useEffect(() => {
    loadSucursales();
  }, []);

  useEffect(() => {
    setPage(0);
    loadFiches();
  }, [selectedSucursal, fechaDesde, fechaHasta, auditorNombre, limit]);

  useEffect(() => {
    loadFiches();
  }, [page]);

  const handleClearFilters = () => {
    setSelectedSucursal("");
    setFechaDesde("");
    setFechaHasta("");
    setAuditorNombre("");
    setPage(0);
  };

  const handleViewDetails = (ficha: Ficha) => {
    setSelectedFicha(ficha);
    setOpenDetail(true);
  };

  const handleDownload = (url: string) => {
    window.open(url, "_blank");
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("es-AR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getSeverityColor = (score: number) => {
    if (score >= 4) return "#22c55e"; // green
    if (score >= 3) return "#eab308"; // yellow
    return "#ef4444"; // red
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, fontWeight: "bold" }}>
        📄 Fichas de Auditoría
      </Typography>

      {/* Filters */}
      <Card sx={{ mb: 3, p: 2 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 2 }}>
          <FormControl fullWidth>
            <InputLabel>Sucursal</InputLabel>
            <Select value={selectedSucursal} onChange={(e) => setSelectedSucursal(e.target.value)} label="Sucursal">
              <MenuItem value="">Todas</MenuItem>
              {sucursales.map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <TextField
            label="Auditor"
            value={auditorNombre}
            onChange={(e) => setAuditorNombre(e.target.value)}
            placeholder="Buscar por auditor..."
          />

          <TextField
            label="Desde"
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />

          <TextField
            label="Hasta"
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />

          <Button
            variant="outlined"
            startIcon={<FilterListOff />}
            onClick={handleClearFilters}
            sx={{ alignSelf: "center" }}
          >
            Limpiar
          </Button>
        </Box>
      </Card>

      {/* Fiches Grid */}
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : fiches.length === 0 ? (
        <Alert severity="info">No hay fichas que coincidan con los filtros.</Alert>
      ) : (
        <>
          <Typography variant="subtitle2" sx={{ mb: 2, color: "text.secondary" }}>
            {fiches.length} resultado(s)
          </Typography>

          <Grid container spacing={2} sx={{ mb: 4 }}>
            {fiches.map((ficha) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={ficha.id}>
                <Card
                  sx={{
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    transition: "all 0.3s",
                    "&:hover": { boxShadow: 4, transform: "translateY(-4px)" },
                  }}
                >
                  <CardContent sx={{ flexGrow: 1 }}>
                    {/* Score Badge */}
                    <Box sx={{ mb: 2, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <Chip
                        label={`${ficha.puntuacion_promedio.toFixed(1)}/5`}
                        sx={{
                          bgcolor: getSeverityColor(ficha.puntuacion_promedio),
                          color: "white",
                          fontWeight: "bold",
                        }}
                      />
                      <Typography variant="caption" sx={{ color: "text.secondary" }}>
                        {formatDate(ficha.fecha_auditoria)}
                      </Typography>
                    </Box>

                    {/* Details */}
                    <Typography variant="subtitle2" sx={{ fontWeight: "bold", mb: 1 }}>
                      {ficha.sucursal_id}
                    </Typography>

                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      <strong>Auditor:</strong> {ficha.auditor_nombre}
                    </Typography>

                    <Typography variant="body2" sx={{ mb: 1 }}>
                      <strong>Responsable:</strong> {ficha.responsable_desvios || "-"}
                    </Typography>

                    {/* Evidence counts */}
                    <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap" }}>
                      <Chip
                        label={`${ficha.desvios_count} desvío(s)`}
                        variant="outlined"
                        size="small"
                        color={ficha.desvios_count > 0 ? "error" : "success"}
                      />
                      <Chip
                        label={`${ficha.fotos_count} foto(s)`}
                        variant="outlined"
                        size="small"
                      />
                    </Box>
                  </CardContent>

                  <CardActions sx={{ pt: 0 }}>
                    <Button
                      size="small"
                      startIcon={<Visibility />}
                      onClick={() => handleViewDetails(ficha)}
                    >
                      Ver
                    </Button>
                    <Button
                      size="small"
                      startIcon={<Download />}
                      onClick={() => handleDownload(ficha.url_pdf)}
                      color="primary"
                    >
                      PDF
                    </Button>
                  </CardActions>
                </Card>
              </Grid>
            ))}
          </Grid>

          {/* Pagination */}
          <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mt: 4 }}>
            <Button
              variant="outlined"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Anterior
            </Button>
            <Typography sx={{ alignSelf: "center", px: 2 }}>
              Página {page + 1}
            </Typography>
            <Button
              variant="outlined"
              disabled={fiches.length < limit}
              onClick={() => setPage(page + 1)}
            >
              Siguiente
            </Button>
          </Box>
        </>
      )}

      {/* Detail Dialog */}
      <Dialog open={openDetail} onClose={() => setOpenDetail(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: "bold" }}>
          Ficha de Auditoría - {selectedFicha?.sucursal_id}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {selectedFicha && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                  Sucursal
                </Typography>
                <Typography variant="body2">{selectedFicha.sucursal_id}</Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                  Auditor
                </Typography>
                <Typography variant="body2">{selectedFicha.auditor_nombre}</Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                  Responsable Desvíos
                </Typography>
                <Typography variant="body2">{selectedFicha.responsable_desvios || "-"}</Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                  Fecha
                </Typography>
                <Typography variant="body2">{formatDate(selectedFicha.fecha_auditoria)}</Typography>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                  Puntuación Promedio
                </Typography>
                <Box
                  sx={{
                    display: "inline-block",
                    bgcolor: getSeverityColor(selectedFicha.puntuacion_promedio),
                    color: "white",
                    px: 2,
                    py: 1,
                    borderRadius: 1,
                    fontWeight: "bold",
                  }}
                >
                  {selectedFicha.puntuacion_promedio.toFixed(1)}/5
                </Box>
              </Box>

              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                    Desvíos
                  </Typography>
                  <Typography variant="body2" sx={{ color: "error.main", fontWeight: "bold" }}>
                    {selectedFicha.desvios_count}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                    Fotos
                  </Typography>
                  <Typography variant="body2" sx={{ color: "primary.main", fontWeight: "bold" }}>
                    {selectedFicha.fotos_count}
                  </Typography>
                </Box>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDetail(false)}>Cerrar</Button>
          <Button
            variant="contained"
            startIcon={<Download />}
            onClick={() => {
              if (selectedFicha) handleDownload(selectedFicha.url_pdf);
              setOpenDetail(false);
            }}
          >
            Descargar PDF
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
