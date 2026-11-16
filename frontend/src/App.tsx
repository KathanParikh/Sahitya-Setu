import { Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/RequireAuth";
import { AppShell } from "./components/AppShell";
import { missingSettings } from "./config";
import { AnswerView } from "./features/ask/AnswerView";
import { AskTab, HistoryTab } from "./features/ask/Questions";
import { ContentsTab } from "./features/book/ContentsTab";
import { SummaryTab } from "./features/summary/SummaryTab";
import { BookPage } from "./pages/BookPage";
import { LibraryPage } from "./pages/LibraryPage";
import { LoginPage } from "./pages/LoginPage";
import { HelpPage } from "./pages/HelpPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SetupPage } from "./pages/SetupPage";
import { SignUpPage } from "./pages/SignUpPage";

export function App() {
  if (missingSettings.length) return <SetupPage />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<LibraryPage />} />
          <Route path="books/:docId" element={<BookPage />}>
            <Route index element={<AskTab />} />
            <Route path="history" element={<HistoryTab />} />
            <Route path="questions/:entryId" element={<AnswerView />} />
            <Route path="summaries" element={<SummaryTab />} />
            <Route path="contents" element={<ContentsTab />} />
          </Route>
          <Route path="help" element={<HelpPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
