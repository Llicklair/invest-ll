# Contratos de interfaz — Feature 003

Las fronteras del sistema. Todo lo que toca la red o el dinero vive detrás de uno de estos
protocolos, para poder sustituirlo en los tests y para que el motor no lo conozca.

---

## 1 · `DecisionProvider` — la frontera con el LLM

```python
class DecisionProvider(Protocol):
    def decide(self, request: DecisionRequest) -> Decision: ...
    def decide_many(self, requests: Sequence[DecisionRequest]) -> list[Decision]: ...
    @property
    def model(self) -> str: ...
```

**Por qué `decide_many` está en el protocolo desde el principio**: las decisiones de un backtest
son independientes entre sí, y enviarlas en lote cuesta la mitad (research D4). Añadirlo después
obligaría a cambiar todos los implementadores.

| Implementación | Toca la red | Para qué |
|---|---|---|
| `AnthropicProvider` | **Sí** | La real. La única. |
| `CachedProvider` | Solo si falla el caché | Envuelve a otra. Es lo que da reproducibilidad. |
| `RecordedProvider` | No | Lee decisiones guardadas. Tests y repetición de experimentos. |
| `ScriptedProvider` | No | Decisiones fijas para casos límite. |

**Contrato de errores** (FR-011): una respuesta que no encaje en el esquema lanza
`DecisionParseError`. **Nunca** se devuelve una decisión inventada ni una por defecto. Si el
proveedor no responde, `DecisionUnavailableError`.

**Prohibido**: que `decide()` devuelva una decisión con `timestamp` distinto al pedido. Eso sería
mezclar instantes, que es look-ahead con otro nombre.

---

## 2 · `LLMStrategy` — la frontera con el motor

```python
class LLMStrategy:
    def evaluate_universe(self, view: UniverseView) -> str | None: ...
```

**Es el mismo protocolo que `RelativeMomentum`.** No hay nada especial: `run_rotation()` no
distingue una de otra, y por eso los informes son comparables (Principio V).

**Contrato**:

- Solo lee de `view`. El bloqueo de look-ahead es el que ya existe.
- Devuelve un símbolo del universo, o `None` para quedarse fuera.
- Entre puntos de decisión **reutiliza la vigente** (FR-042) — no consulta en cada vela.
- Un fallo del proveedor **detiene el backtest**. No se sustituye por "mantener lo que había": eso
  convertiría un error en un resultado, y el informe diría algo que no ocurrió.

---

## 3 · `Broker` — la frontera con el dinero

```python
class Broker(Protocol):
    @property
    def mode(self) -> OperatingMode: ...
    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult: ...
    def balance(self) -> Mapping[str, Decimal]: ...
```

**El parámetro `confirmation` es obligatorio y no tiene valor por defecto.** No se puede llamar a
`submit()` sin construir una confirmación, y una `Confirmation` se construye con la orden concreta
que autoriza. Autorizar "todas las órdenes" no es representable en el tipo.

Es la traducción de FR-028 a algo que el comprobador de tipos impone, en lugar de a una comprobación
que alguien puede olvidar escribir.

| Implementación | Modo | Efecto |
|---|---|---|
| `SimulatedBroker` | `Simulation` | Nada sale. Por defecto. |
| `CcxtBroker` | `Testnet` o `Real` | Órdenes de verdad. |

**Contrato de seguridad**:

1. `SimulatedBroker.submit()` **nunca** produce una orden real, con ninguna confirmación.
2. `CcxtBroker` comprueba su modo **al enviar**, no al construirse (FR-032).
3. Las credenciales de pruebas y las reales no son intercambiables: usar unas donde tocan las otras
   **falla de forma visible** (FR-048).
4. Ningún mensaje de error, registro ni informe incluye una credencial (FR-034).
5. Pérdida de conexión ⇒ `UNKNOWN`. Nunca `FILLED` ni `REJECTED` por suposición (FR-035).

---

## 4 · `AssetResearcher` — la frontera con los datos fundamentales

```python
class AssetResearcher(Protocol):
    def analyze(self, symbol: str) -> AssetAnalysis: ...
```

**Contrato**: todo `Fact` lleva `source` y `as_of` (FR-017). La narrativa y los escenarios van en
campos aparte de los hechos (FR-049) — quien lee el informe siempre sabe qué puede comprobar.

Para un activo sin entidad detrás (una materia prima, un índice), `facts` describe qué **es**, sin
inventar una empresa (FR-019).

---

## Contrato transversal: los tests no salen a la red

Ya hay un `conftest.py` que bloquea los sockets en toda la suite. Para esta feature eso significa:

- `AnthropicProvider` y `CcxtBroker` **solo** se prueban con dobles.
- Cualquier implementación que intentara salir a la red **falla de forma ruidosa** en el test, no en
  silencio.
- Un test que necesite red de verdad lleva `@pytest.mark.network` y queda fuera de la suite normal.

Es la misma garantía estructural que hoy protege al motor: no depende de que nadie se acuerde.
