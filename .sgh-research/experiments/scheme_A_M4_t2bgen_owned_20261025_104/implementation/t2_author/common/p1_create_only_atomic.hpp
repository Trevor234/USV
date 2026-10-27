// SPDX-License-Identifier: MIT
// Linux create-only publication. The caller pins a nofollow parent directory FD.
#pragma once
#include <fcntl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <cerrno>
#include <string>
#include <system_error>

namespace p1_create_only {
class PublicationAmbiguousError : public std::system_error {
public:
  PublicationAmbiguousError(int error, const std::string & path)
  : std::system_error(error, std::generic_category(),
      "target visible; directory durability unconfirmed: " + path), target_path(path) {}
  const std::string target_path;
  const bool target_visible = true;
};

// No fallback to link/unlink or overwriting rename: both break the reader's
// single-link/create-only contract. An unsupported platform fails before commit.
inline void rename_noreplace(int directory, const std::string & temporary,
  const std::string & target)
{
#if defined(__linux__) && defined(SYS_renameat2)
  constexpr unsigned int rename_noreplace_flag = 1;
  if (::syscall(SYS_renameat2, directory, temporary.c_str(), directory,
      target.c_str(), rename_noreplace_flag) != 0) {
    const int error = errno;
    throw std::system_error(error, std::generic_category(),
      "create-only destination exists or atomic no-replace rename failed");
  }
#else
  (void)directory; (void)temporary; (void)target;
  throw std::system_error(ENOSYS, std::generic_category(), "create-only renameat2 unsupported");
#endif
}

inline void write_create_only_at(int directory, const std::string & target,
  const std::string & temporary, const std::string & bytes, const std::string & path)
{
  const int file = ::openat(directory, temporary.c_str(),
    O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
  if (file < 0) {
    throw std::system_error(errno, std::generic_category(), "create-only temporary create failed");
  }
  // This call exclusively owns its temporary pathname. Rename removes that
  // name before target visibility; post-commit errors never delete the target.
  bool published = false;
  try {
    size_t done = 0;
    while (done < bytes.size()) {
      const ssize_t count = ::write(file, bytes.data() + done, bytes.size() - done);
      if (count < 0 && errno == EINTR) {continue;}
      if (count <= 0) {
        throw std::system_error(count < 0 ? errno : EIO, std::generic_category(),
          "create-only output write failed");
      }
      done += static_cast<size_t>(count);
    }
    if (::fsync(file) != 0) {
      throw std::system_error(errno, std::generic_category(), "create-only file fsync failed");
    }
    rename_noreplace(directory, temporary, target);
    published = true;
    if (::fsync(directory) != 0) {
      throw PublicationAmbiguousError(errno, path);
    }
  } catch (...) {
    if (!published) {(void)::unlinkat(directory, temporary.c_str(), 0);}
    (void)::close(file);
    throw;
  }
  (void)::close(file);
}
}  // namespace p1_create_only
