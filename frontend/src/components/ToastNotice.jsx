import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import CloseRounded from "@mui/icons-material/CloseRounded";

export default function ToastNotice({ notice, onClose }) {
  return (
    <Snackbar
      key={notice?.id}
      open={Boolean(notice)}
      anchorOrigin={{ vertical: "top", horizontal: "right" }}
      autoHideDuration={notice?.severity === "error" ? null : 10000}
      onClose={(_event, reason) => { if (reason !== "clickaway") onClose(); }}
      sx={{ top: { xs: 64, sm: 72 }, maxWidth: 440 }}
    >
      <Alert
        severity={notice?.severity || "error"}
        sx={{ width: "100%", bgcolor: "background.paper", border: 1, borderColor: "divider", boxShadow: 3, whiteSpace: "pre-line" }}
        action={
          <>
            {notice?.retry && (
              <Button size="small" color="inherit" onClick={() => { onClose(); notice.retry(); }}>
                Retry
              </Button>
            )}
            <IconButton size="small" aria-label="Dismiss notification" color="inherit" onClick={onClose}>
              <CloseRounded fontSize="small" />
            </IconButton>
          </>
        }
      >
        {notice?.message}
      </Alert>
    </Snackbar>
  );
}
