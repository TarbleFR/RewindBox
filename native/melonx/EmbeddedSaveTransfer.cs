using System;
using System.Globalization;
using System.IO;
using Path = System.IO.Path;
using System.Linq;
using System.Text.Json;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Shim;
using LibHac.Ns;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.FileSystem;
using Ryujinx.HLE.HOS.Services.Account.Acc;

namespace Ryujinx.Library;

partial class Library
{
    private static void EmbeddedStorageInfo(Utf8JsonWriter json)
    {
        json.WriteString("root", AppDataManager.BaseDirPath);
        json.WriteString("nand", VirtualFileSystem.GetNandPath());
        json.WriteStartArray("profiles");
        foreach (var profile in _accountManager.GetAllUsers())
        {
            json.WriteStartObject();
            json.WriteString("id", profile.UserId.ToString());
            json.WriteString("name", profile.Name);
            json.WriteEndObject();
        }
        json.WriteEndArray();
    }

    // LibHac owns the mapping title/profile -> save ID. Neither Flutter nor a
    // directory name may invent an ID in bis/user/save. Same 0/1 commit layout
    // as the upstream get_save_data_path ABI, with an explicit user selection.
    private static void EmbeddedSaveTarget(string request, Utf8JsonWriter json)
    {
        using var document = JsonDocument.Parse(request);
        string titleText = document.RootElement.GetProperty("titleId").GetString();
        string userText = document.RootElement.GetProperty("profileId").GetString();
        if (titleText?.Length != 16 || !ulong.TryParse(titleText, NumberStyles.HexNumber,
            CultureInfo.InvariantCulture, out ulong title) || title == 0 ||
            userText?.Length != 32) throw new ArgumentException("Invalid save association.");
        var user = new Ryujinx.HLE.HOS.Services.Account.Acc.UserId(userText);
        if (!_accountManager.GetAllUsers().Any(profile => profile.UserId == user)) throw new ArgumentException("Unknown user profile.");
        var fsUser = user.ToLibHac();
        var filter = SaveDataFilter.Make(title, SaveDataType.Account, fsUser,
            saveDataId: default, index: default);
        var client = _libHacHorizonManager.RyujinxClient;
        var result = client.Fs.FindSaveDataWithFilter(out SaveDataInfo info, SaveDataSpaceId.User, in filter);
        if (ResultFs.TargetNotFound.Includes(result))
        {
            BlitStruct<ApplicationControlProperty> holder = new(1);
            ref ApplicationControlProperty control = ref holder.Value;
            control.UserAccountSaveDataSize = 0x4000;
            control.UserAccountSaveDataJournalSize = 0x4000;
            var uid = user.ToLibHacUid();
            client.Fs.EnsureApplicationSaveData(out _, new LibHac.Ncm.ApplicationId(title),
                in control, in uid).ThrowIfFailure();
            result = client.Fs.FindSaveDataWithFilter(out info, SaveDataSpaceId.User, in filter);
        }
        result.ThrowIfFailure();
        string save = Path.Combine(VirtualFileSystem.GetNandPath(), "user", "save", $"{info.SaveDataId:x16}");
        string committed = Path.Combine(save, "0");
        // Return the entire save transaction root. Both commit and working
        // trees are replaced together, retaining LibHac extra-data metadata.
        json.WriteString("path", save);
        json.WriteString("dataPath", Directory.Exists(committed) ? committed : Path.Combine(save, "1"));
        json.WriteString("titleId", titleText);
        json.WriteString("profileId", userText);
    }
}
