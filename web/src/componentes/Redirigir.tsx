"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Una ruta vieja que ahora vive en otro sitio (docs/panel-v5.md, seccion 2). El export es estatico:
 * no hay redirecciones del servidor, asi que se hace en el cliente, conservando la consulta y el
 * ancla (`/invertir/#accion-x` → `/plan/invertir/#accion-x`). Mientras, se dice adonde fue.
 */
export function Redirigir({ a, que }: { a: string; que: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(`${a}${window.location.search}${window.location.hash}`);
  }, [a, router]);
  return (
    <p className="py-10 text-[0.9375rem] text-tinta-suave" role="status">
      {que} se ha movido.{" "}
      <Link href={a} className="font-semibold text-marca underline underline-offset-4">
        Ir allí
      </Link>
    </p>
  );
}
