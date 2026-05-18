import { redirect } from "next/navigation";
import LoginForm from "./_components/LoginForm";

export default function LoginPage() {
  if (!process.env.ADMIN_SECRET) redirect("/");
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <LoginForm />
    </div>
  );
}
