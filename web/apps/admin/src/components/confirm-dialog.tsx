"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type Options = {
  title?: string;
  description: string;
  confirmLabel?: string;
};

type DialogState = Options & {
  resolve: (ok: boolean) => void;
};

let _setState: ((s: DialogState | null) => void) | null = null;

/** Call from anywhere to show a confirm dialog. Returns true if confirmed. */
export function confirmDialog(opts: Options): Promise<boolean> {
  return new Promise((resolve) => {
    _setState?.({ ...opts, resolve });
  });
}

/** Mount once in the layout. */
export function ConfirmDialogProvider() {
  const [state, setState] = useState<DialogState | null>(null);
  _setState = setState;

  function handleClose(ok: boolean) {
    state?.resolve(ok);
    setState(null);
  }

  return (
    <AlertDialog open={!!state} onOpenChange={(open) => { if (!open) handleClose(false); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {state?.title ?? "確認操作"}
          </AlertDialogTitle>
          <AlertDialogDescription>{state?.description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => handleClose(false)}>取消</AlertDialogCancel>
          <AlertDialogAction onClick={() => handleClose(true)}>
            {state?.confirmLabel ?? "確認"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
