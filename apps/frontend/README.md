# Doc. Chat

Doc. Chat is a ChatGPT-style document-aware chat interface built with Next.js. It supports multi-conversation chat, theme switching, responsive sidebars, and an in-app document viewer for PDFs, TXT files, and DOCX files.

The UI is designed to feel familiar to ChatGPT while remaining lightweight, extensible, and developer-friendly.

## ✨ Features

### 💬 Chat Experience

- Full-screen, responsive chat layout (ChatGPT-style)
- Independent scrolling:
  - Conversation sidebar
  - Chat message history
  - Sticky message composer
- Conversations automatically reorder by most recent activity
- Active conversation is visually highlighted (theme-aware)

### 📂 Attachments & Document Viewer

- Click attachments to open them in a right-side document viewer
- Supported formats:
  - PDF (iframe/embed)
  - TXT (rendered text)
  - DOCX (client-side preview)
- Attachment viewer replaces the left sidebar to maximize space
- Back arrow restores the conversation sidebar
- Dropdown in viewer header lets you switch between all attachments in the conversation
- Dropdown always renders above document content (no z-index issues)

### 🎨 Theming

- Light mode + Dark mode
- Theme controlled via a Settings (gear) icon
- Theme selection persists across reloads
- Fully tokenized color system using CSS variables

### 📱 Responsive Design

- Sidebar widths adapt using responsive clamps
- On small screens:
  - Left sidebar collapses automatically
  - Right document viewer hides when space is insufficient
  - No horizontal scrolling or layout breakage on resize

### 🧠 UX Principles

- Only one sidebar (left or right) visible at a time
- Chat remains the primary focus at all times
- No “double scrolling” or layout jank
- Minimal UI changes, maximum clarity

### 🚧 Future Ideas (Optional)

- Search within documents
- Per-document chat context
- Drag-and-drop uploads
- Conversation export
- Auth + persistence backend

## 🧱 Tech Stack

- Next.js (App Router)
- React + TypeScript
- Tailwind CSS
- shadcn/ui + Radix
- Client-side DOCX parsing (docx-preview / mammoth)

## 📁 Project Structure (Simplified)

```
app/
  layout.tsx
  page.tsx
  globals.css

components/
  chat/
    chat-app.tsx
    chat-thread.tsx
    sidebar.tsx
    attachment-viewer.tsx
  ui/

lib/
  config.ts
  utils.ts
```

## Getting started

### Requirements

- Node.js 18+
- npm, pnpm, or yarn

### Quick start

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Configuration

The app reads an optional API base URL for backend integration:

```
NEXT_PUBLIC_API_BASE_URL=
```

## Notes

- Conversations, messages, attachments, and settings load from the backend API.
