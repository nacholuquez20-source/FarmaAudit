# Phase 3: Photo Capture and Validation

**Status**: ✅ Implementado y testeado  
**Files Created**: 
- `photo_validator.py` - Photo validation module
- `test_photo_validator.py` - Validator unit tests
- `test_photo_evidence_flow.py` - Integration tests

**Modified Files**:
- `audit_handlers.py` - Enhanced photo handling with validation
- `audit_session.py` - No changes needed (FotoEvidence.validated field already existed)

---

## 🎯 Overview

Phase 3 implements automatic photo validation and bloque assignment for audit evidence collection:

### Key Features
1. **Automatic Photo Download**: Downloads media from Meta CDN using `media_id`
2. **Quality Validation**: Checks photo quality (size, blur, format)
3. **Intelligent Feedback**: Provides clear error messages for invalid photos
4. **Bloque Linking**: User specifies which area (bloque) the photo is from
5. **Desvio Creation**: Automatically creates deviations linked to photos and bloques

---

## 🔍 Photo Validation Rules

| Rule | Min/Max | Error Message |
|------|---------|---------------|
| File Size | < 10MB | "Archivo muy grande" |
| Dimensions | ≥ 320x320 px | "Foto muy pequeña" |
| Blur (Laplacian) | > 80 variance | "Foto borrosa" |
| MIME Type | image/* | "Eso no es una foto" |
| Valid Image | Can parse | "No puedo procesar" |

### Validation Algorithm

**Blur Detection**: Uses Laplacian edge detection variance method
- Converts image to grayscale
- Applies FIND_EDGES filter (PIL)
- Calculates variance of edge pixels
- High variance = sharp image, Low variance = blurry image

```python
# Example: Blur score calculation
edges = image.filter(ImageFilter.FIND_EDGES)
pixels = list(edges.getdata())
mean = sum(pixels) / len(pixels)
variance = sum((p - mean)**2 for p in pixels) / len(pixels)
# variance > 80.0 = sharp; < 80.0 = blurry
```

---

## 📱 WhatsApp Conversation Flow

### Phase 3 Conversation (EVIDENCE state)

```
Bot: "✓ Auditoría de puntuaciones completada!
      Ahora necesito fotos de los problemas encontrados.
      
      Áreas con problemas (3-4):
      • Limpieza (4/5)
      • Stock (3/5)
      
      Envía fotos o escribe 'Listo' cuando termines"

User: [Envía foto]

Bot: "✓ Foto guardada correctamente.
      ¿De qué área es? (Limpieza, Stock, Ofertas, Burbujas)"

User: "Stock"

Bot: "✓ Foto vinculada a Stock
      ¿Cuál es el problema observado?
      (O envía 'Listo' si terminas)"

User: "Falta reposición de productos"

Bot: "✓ Guardado: Falta reposición de productos
      ¿Otra foto o escribe 'Listo'?"

User: "Listo"

Bot: "[SUMMARY displayed]"
```

### Error Handling

**Blurry Photo**:
```
User: [Envía foto borrosa]

Bot: "❌ La foto está borrosa. Por favor envía una más clara.
      
      Intenta de nuevo o escribe 'Listo' para continuar."
```

**Invalid Format**:
```
User: [Envía PDF en lugar de foto]

Bot: "❌ Eso no es una foto. Por favor envía una imagen.
      
      Intenta de nuevo o escribe 'Listo' para continuar."
```

---

## 🔧 Implementation Details

### PhotoValidator Class

```python
class PhotoValidator:
    MIN_WIDTH = 320           # Mínimo ancho en píxeles
    MIN_HEIGHT = 320          # Mínimo alto en píxeles
    MAX_FILE_SIZE = 10MB      # Tamaño máximo de archivo
    BLUR_THRESHOLD = 80.0     # Varianza mínima para detectar nitidez
    
    @staticmethod
    def validate_media_bytes(
        media_bytes: bytes,
        mime_type: str = "image/jpeg"
    ) -> PhotoValidationResult:
        """Validate photo and return result."""
```

### PhotoValidationResult

```python
@dataclass
class PhotoValidationResult:
    is_valid: bool              # ¿Foto válida?
    message: str                # Mensaje del usuario
    issues: list[str]           # Detalles técnicos para logging
```

---

## 📊 Enhanced handle_evidence() Flow

### When Image Received

```
1. Check media_id exists
2. Download media from Meta CDN
   └─ meta_client.download_media_with_metadata(media_id)
3. Validate media
   └─ PhotoValidator.validate_media_bytes(bytes, mime_type)
4. If invalid:
   └─ Send error message
   └─ Ask to try again or skip
5. If valid:
   └─ Create FotoEvidence(validated=True)
   └─ Store in session.fotos
   └─ Ask for bloque
```

### When Text Received

```
1. Check if "Listo" → Move to SUMMARY
2. Check if bloque name (limpieza/stock/ofertas/burbujas)
   └─ Assign to last photo
   └─ Ask for problem description
3. Otherwise:
   └─ Create desvio for last photo's bloque
   └─ Save desvio
```

---

## 🧪 Test Results

All tests pass successfully:

### test_photo_validator.py
- ✅ Valid photo acceptance
- ✅ Small photo rejection (< 320x320)
- ✅ Wrong MIME type rejection
- ✅ Corrupted image rejection
- ✅ Blurry photo detection

### test_photo_evidence_flow.py
- ✅ Photo evidence collection with validation
- ✅ Photo bloque assignment
- ✅ Multiple photos with different bloques
- ✅ Evidence to summary transition

---

## 📝 Code Changes

### audit_handlers.py

**New Imports**:
```python
from photo_validator import PhotoValidator, PhotoValidationResult
```

**Updated handle_evidence()**:
- Photo download using `meta_client.download_media_with_metadata()`
- Validation using `PhotoValidator.validate_media_bytes()`
- Bloque assignment detection for text inputs
- Desvio creation linked to bloques and photos

**New Return States**:
- `no_media_id` - Falta media_id
- `photo_invalid` - Foto no válida
- `photo_download_error` - Error descargando foto
- `bloque_assigned` - Bloque asignado a foto

---

## 🚀 Integration Checklist

- [x] Create `photo_validator.py`
- [x] Update `audit_handlers.py` with validation
- [x] Test photo validation
- [x] Test evidence flow integration
- [x] Emoji encoding for Windows ✓

**Next Phase**: Phase 4 - Database integration and summary finalization

---

## 📋 Phase 3 Complete

The photo capture and validation system is production-ready:

✅ Handles Meta CDN media download
✅ Validates photo quality (size, blur, format)
✅ Provides intelligent user feedback
✅ Supports multiple photos per session
✅ Links photos to bloques
✅ Creates desvios automatically
✅ All edge cases tested
✅ Windows emoji encoding fixed

