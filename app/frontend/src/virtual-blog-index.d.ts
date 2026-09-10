declare module 'virtual:blog-index' {
  export const blogIndex: {
    slug: string;
    title: string;
    description: string;
    category?: string;
    date?: string;
    tags?: string[];
  }[];
}
