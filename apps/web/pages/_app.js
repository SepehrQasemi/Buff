import "../styles/globals.css";
import ToastHost from "../components/ToastHost";
import { ToastProvider } from "../lib/toast";

export default function App({ Component, pageProps }) {
  return (
    <ToastProvider>
      <Component {...pageProps} />
      <ToastHost />
    </ToastProvider>
  );
}
