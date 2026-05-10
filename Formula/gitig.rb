class Gitig < Formula
  include Language::Python::Virtualenv

  desc "Ignorant CLI for generating .gitignore and LICENSE files"
  homepage "https://github.com/verylongdelay/gitig"
  url "https://github.com/VeryLongDelay/gitig/archive/refs/tags/v0.0.1.tar.gz"
  sha256 "1790018476edf6f0972495a05dbe2dc0217d1a9c283ecdc61228e808f69b96e8"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"gitig", "selftest"
    system bin/"gitig", "help"
  end
end

