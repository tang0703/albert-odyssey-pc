using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;

namespace Ao.SourceContracts
{
    // Pure C#: no Unity types, animation callbacks, clocks or mutable game state.
    public readonly struct SourceIdentity
    {
        public readonly string Path;
        public readonly long Bytes;
        public readonly string Sha256;
        public SourceIdentity(string path, long bytes, string sha256)
        { Path = path; Bytes = bytes; Sha256 = sha256; }
    }

    public static class SourceGuard
    {
        public static string Hash(byte[] bytes)
        {
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }

        public static string SafePath(string directory, string relative)
        {
            if (string.IsNullOrEmpty(relative) || relative.Contains('\\') || relative.Contains(':') ||
                relative.Split('/').Any(p => p == "" || p == "." || p == ".."))
                throw new InvalidDataException("Unsafe source path: " + relative);
            string root = System.IO.Path.GetFullPath(directory).TrimEnd(System.IO.Path.DirectorySeparatorChar);
            string file = System.IO.Path.GetFullPath(System.IO.Path.Combine(root, relative));
            if (!file.StartsWith(root + System.IO.Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Source path outside root");
            for (string p = file; p != null; p = System.IO.Path.GetDirectoryName(p))
            {
                if ((File.Exists(p) || Directory.Exists(p)) &&
                    (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Redirected source path: " + p);
                if (string.Equals(p, root, StringComparison.OrdinalIgnoreCase)) break;
            }
            return file;
        }

        public static Dictionary<string, byte[]> Load(string directory,
            IReadOnlyList<SourceIdentity> approved, bool editorMetadata = false)
        {
            // Validate complete closure before exposing any bytes to a caller.
            var paths = new HashSet<string>(approved.Select(x => x.Path), StringComparer.Ordinal);
            if (paths.Count != approved.Count) throw new InvalidDataException("Duplicate source identity");
            foreach (var identity in approved) SafePath(directory, identity.Path);
            foreach (string file in FilesWithoutRedirects(directory))
            {
                string name = file.Substring(System.IO.Path.GetFullPath(directory).TrimEnd('\\', '/').Length + 1).Replace('\\', '/');
                SafePath(directory, name);
                if (editorMetadata && name.EndsWith(".meta", StringComparison.Ordinal)) continue;
                if (!paths.Contains(name)) throw new InvalidDataException("Unapproved runtime source: " + name);
            }
            var loaded = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            foreach (var identity in approved)
            {
                byte[] raw = File.ReadAllBytes(SafePath(directory, identity.Path));
                if (raw.LongLength != identity.Bytes || Hash(raw) != identity.Sha256)
                    throw new InvalidDataException("Source bytes changed: " + identity.Path);
                loaded.Add(identity.Path, raw);
            }
            return loaded;
        }

        private static IEnumerable<string> FilesWithoutRedirects(string directory)
        {
            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Redirected source entry: " + entry);
                if ((attributes & FileAttributes.Directory) != 0)
                { foreach (string file in FilesWithoutRedirects(entry)) yield return file; }
                else yield return entry;
            }
        }
    }

    public static class SourceInteger
    {
        public static int Signed16(int value) => unchecked((short)value);
        public static int Divide16(int value) => value / 16;
        public static int Word(byte[] raw, int offset) => (raw[offset] << 8) | raw[offset + 1];
        public static void PutWord(byte[] raw, int offset, int value)
        { raw[offset] = unchecked((byte)(value >> 8)); raw[offset + 1] = unchecked((byte)value); }
    }
}
