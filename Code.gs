// Code.gs

// Esta función se ejecuta cuando alguien visita la URL del web app.
function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index');
}

/**
 * Prepara el contenido del reporte para la descarga.
 * A MODO DE EJEMPLO, crea un string en formato CSV.
 * --- REEMPLAZA ESTA LÓGICA CON LA TUYA ---
 * @return {string} El contenido del archivo a descargar.
 */
function generateReportData() {
  const headers = "ID de Producto,Nombre,Stock,Precio\n";
  const rows = [
    ["PROD-001", "Laptop Modelo X", 25, 1200.50],
    ["PROD-002", "Mouse Inalámbrico", 150, 25.00],
    ["PROD-003", "Teclado Mecánico", 75, 89.99]
  ];

  let csvContent = headers;
  rows.forEach(function(row) {
    csvContent += row.join(",") + "\n";
  });
  
  return csvContent;
}
