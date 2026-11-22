%define major 0
%define libname %mklibname bcc %{major}
%define devname %mklibname bcc -d

# "fix" underlinking:
%global _disable_ld_no_undefined 1
# luajit is not available for some architectures
%bcond_without lua

Summary:	BPF Compiler Collection (BCC)
Name:		bcc
Version:	0.37.0
Release:	1
License:	Apache-2.0
Group:		Development/Kernel
Url:		https://github.com/iovisor/bcc
Source0:	https://github.com/iovisor/bcc/releases/download/v%{version}/%{name}-src-with-submodule-%{version}.tar.gz
# within source archive, cd libbpf-tools/blazesym
# cargo vendor -s capi/Cargo.toml
# tar -cJvf bcc-VERSION-libbpftool-blazesym-vendor.tar.xz
Source1:    %{name}-%{version}-libbpftool-blazesym-vendor.tar.xz
#patch taken from Fedora, adjusted file path to match what the source archive gives us
Patch:		Fix-build-with-LLVM-23.patch

BuildRequires:	bison
BuildRequires:	cmake
BuildRequires:  make
BuildRequires:	rust-packaging
BuildRequires:	git
%if %{with lua}
BuildRequires:	luajit
BuildRequires:	pkgconfig(luajit)
%endif
BuildRequires:	cmake(clang)
BuildRequires:	%{_lib}bpf-static-devel
BuildRequires:	cmake(llvm)
BuildRequires:	python%{pyver}dist(setuptools)
BuildRequires:  python%{pyver}dist(wheel)
BuildRequires:  python%{pyver}dist(build)
BuildRequires:	pkgconfig(libbpf)
BuildRequires:	pkgconfig(libelf)
BuildRequires:	pkgconfig(libfl)
BuildRequires:	pkgconfig(liblzma)
BuildRequires:	pkgconfig(libxml-2.0)
BuildRequires:	pkgconfig(libzstd)
BuildRequires:	pkgconfig(ncursesw)
BuildRequires:	pkgconfig(python3)
Requires:	%{name}-tools = %{EVRD}

%description
BCC is a toolkit for creating efficient kernel tracing and manipulation
programs, and includes several useful tools and examples. It makes use of
extended BPF (Berkeley Packet Filters), formally known as eBPF, a new feature
that was first added to Linux 3.15. BCC makes BPF programs easier to write,
with kernel instrumentation in C (and includes a C wrapper around LLVM), and
front-ends in Python and lua. It is suited for many tasks, including
performance analysis and network traffic control.

%package devel
Summary:        Shared library for BPF Compiler Collection (BCC)
Requires:       %{name}
Suggests:       elfutils-debuginfod-client
%description devel
The %{name}-devel package contains libraries and header files for developing
application that use BPF Compiler Collection (BCC).
#----
%package doc
Summary:        Examples for BPF Compiler Collection (BCC)
Recommends:     python-%{name}
Recommends:     %{name}-lua
BuildArch:      noarch
%description doc
Examples for BPF Compiler Collection (BCC)
#----
%package -n python-%{name}
Summary:        Python3 bindings for BPF Compiler Collection (BCC)
Requires:       %{name}
BuildArch:      noarch
%description -n python-%{name}
Python3 bindings for BPF Compiler Collection (BCC)
#----
%if %{with lua}
%package lua
Summary:        Standalone tool to run BCC tracers written in Lua
Requires:       %{name}
%description lua
Standalone tool to run BCC tracers written in Lua
%endif
#----
%package tools
Summary:        Command line tools for BPF Compiler Collection (BCC)
Requires:       %{name}
Requires:       python-%{name}
Requires:       python%{pyver}dist(netaddr)
%description tools
Command line tools for BPF Compiler Collection (BCC)
#----
%package -n libbpf-tools
Summary:        Command line libbpf tools for BPF Compiler Collection (BCC)
BuildRequires:  pkgconfig(libbpf)
BuildRequires:	%{_lib}bpf-static-devel
BuildRequires:  bpftool
%description -n libbpf-tools
Command line libbpf tools for BPF Compiler Collection (BCC)

%prep
%autosetup -p1 -n %{name}-src-with-submodule-%{version}
tar -xf %{S:1}
mv vendor %{name}/libbpf-tools/blazesym
cat >> %{name}/libbpf-tools/blazesym/.cargo/config.toml << EOF
[source.crates-io]
replace-with = "vendored-sources"

[source."git+https://github.com/libbpf/vmlinux.h.git?rev=a9c092aa771310bf8b00b5018f7d40a1fdb6ec82"]
git = "https://github.com/libbpf/vmlinux.h.git"
rev = "a9c092aa771310bf8b00b5018f7d40a1fdb6ec82"
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "vendor"
EOF

%build
cd %{name}

# bcc stamps its version into the python bindings via "git describe".
# Building from the release tarball there is no .git, so the fallback
# placeholder ("0.0.0+GITDIR-N") ends up as bcc.__version__, which breaks
# consumers that check it (proton-vpn-daemon requires >= 0.26.0).
# Seed a throwaway repo tagged with the real (no 'v' prefix) version.
git init -q .
git add -A
git -c user.name=openmandriva -c user.email=build@openmandriva.org commit -qm "bcc %{version}"
git tag v%{version}

pushd libbpf-tools/blazesym
#cargo build --release --offline
popd

mkdir builddir
pushd builddir
cmake -S .. -B . \
    -D CMAKE_BUILD_TYPE=None \
    -D CMAKE_INSTALL_PREFIX=/usr \
    -Wno-author \
    -D CMAKE_USE_LIBBPF_PACKAGE=ON \
    -D ENABLE_LLVM_SHARED=ON \
    -D ENABLE_TESTS=OFF \
    -D RUN_LUA_TESTS=OFF
cmake --build .
popd

pushd libbpf-tools;
%make_build USE_BLAZESYM=0 BPFTOOL=bpftool LIBBPF_OBJ=%{_libdir}/libbpf.a CFLAGS="%{optflags}" LDFLAGS="%{build_ldflags}"
%make_install DESTDIR=./tmp-install prefix=
(
    cd tmp-install/bin
    for file in *; do
        mv $file bpf-$file
    done
    # now fix the broken symlinks
    for file in `find . -type l`; do
        dest=$(readlink "$file")
        ln -s -f bpf-$dest $file
    done
)
popd

%install
cd %{name}
cd builddir
make install/strip DESTDIR=%{buildroot}
# mangle shebangs
find %{buildroot}/usr/share/%{name}/{tools,examples} -type f -exec \
    sed -i -e '1 s|^#!/usr/bin/python$|#!'%{__python}'|' \
           -e '1 s|^#!/usr/bin/env python$|#!'%{__python}'|' {} \;

# Move man pages to the right location
mkdir -p %{buildroot}%{_mandir}
mv %{buildroot}%{_datadir}/%{name}/man/* %{buildroot}%{_mandir}/

# Avoid conflict with other manpages
# https://bugzilla.redhat.com/show_bug.cgi?id=1517408
for i in `find %{buildroot}%{_mandir} -name "*.gz"`; do
  tname=$(basename $i)
  rename $tname %{name}-$tname $i
done

mkdir -p %{buildroot}%{_docdir}/%{name}
mv %{buildroot}%{_datadir}/%{name}/examples %{buildroot}%{_docdir}/%{name}/

mkdir -p %{buildroot}%{_sbindir}
# We cannot use `install` because some of the tools are symlinks and `install`
# follows those. Since all the tools already have the correct permissions set,
# we just need to copy them to the right place while preserving those
cp -a ../libbpf-tools/tmp-install/bin/* %{buildroot}%{_sbindir}/

%post -p /sbin/ldconfig
%postun -p /sbin/ldconfig

%files
%doc %{name}/README.md
%license %{name}/LICENSE.txt
%{_libdir}/lib%{name}.so.*
%{_libdir}/lib%{name}_bpf.so.*

%files devel
%{_libdir}/*.a
%{_libdir}/lib%{name}.so
%{_libdir}/lib%{name}_bpf.so
%{_libdir}/pkgconfig/lib%{name}.pc
%{_includedir}/%{name}/

%files -n python-%{name}
%{python3_sitelib}/%{name}*

%files doc
%dir %{_docdir}/%{name}
%doc %{_docdir}/%{name}/examples/

%files tools
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/tools/
%{_datadir}/%{name}/introspection/
%{_mandir}/man8/*

%if %{with lua}
%files lua
%{_bindir}/%{name}-lua
%endif

%files -n libbpf-tools
%{_sbindir}/bpf-*
