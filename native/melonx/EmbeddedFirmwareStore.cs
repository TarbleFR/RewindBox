using System;
using System.IO;

namespace Ryujinx.HLE.FileSystem;

// Journal only the owned firmware directory swap. Never delete the last
// firmware before a replacement has been completely validated and extracted.
internal static class EmbeddedFirmwareStore
{
    internal static void Recover(string registered)
    {
        string backup = registered + ".rewindbox-previous";
        string marker = registered + ".rewindbox-transaction";
        if (File.Exists(marker))
        {
            bool firstInstallation = File.ReadAllText(marker) == "empty";
            if (Directory.Exists(backup))
            {
                if (Directory.Exists(registered)) Directory.Delete(registered, true);
                Directory.Move(backup, registered);
            }
            else if (firstInstallation && Directory.Exists(registered))
            {
                Directory.Delete(registered, true);
            }
            File.Delete(marker);
        }
        else if (Directory.Exists(backup))
        {
            // Commit completed; interruption affected only old-data cleanup.
            if (!Directory.Exists(registered)) Directory.Move(backup, registered);
            else TryDeleteBackup(backup);
        }
    }

    internal static void Commit(string extracted, string registered, Action load)
    {
        Recover(registered);
        string backup = registered + ".rewindbox-previous";
        string marker = registered + ".rewindbox-transaction";
        if (Directory.Exists(backup)) throw new IOException("The previous firmware backup could not be retired.");
        using (var journal = new FileStream(marker, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        {
            byte[] initialState = System.Text.Encoding.UTF8.GetBytes(Directory.Exists(registered) ? "previous" : "empty");
            journal.Write(initialState);
            journal.Flush(true);
        }
        try
        {
            if (Directory.Exists(registered)) Directory.Move(registered, backup);
            Directory.Move(extracted, registered);
            load();
            File.Delete(marker);
        }
        catch
        {
            Recover(registered);
            try { load(); } catch { /* preserve the original failure */ }
            throw;
        }
        TryDeleteBackup(backup);
    }

    private static void TryDeleteBackup(string backup)
    {
        if (!Directory.Exists(backup)) return;
        try { Directory.Delete(backup, true); }
        catch (Exception error) { Console.Error.WriteLine("MeloNX old firmware cleanup: " + error.Message); }
    }
}
